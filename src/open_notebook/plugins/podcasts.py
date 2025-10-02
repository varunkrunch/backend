from typing import ClassVar, List, Optional
import json
import os
import subprocess

from loguru import logger
from podcastfy.client import generate_podcast
from pydantic import Field, field_validator, model_validator
import mutagen
from mutagen.mp3 import MP3

from ..config import DATA_FOLDER
from ..domain.notebook import ObjectModel


class PodcastEpisode(ObjectModel):
    table_name: ClassVar[str] = "podcast_episode"
    name: str
    template: str
    instructions: str
    text: str
    audio_file: str
    audio_url: Optional[str] = None
    status: str = "pending"  # pending, completed, failed
    duration: Optional[float] = None  # duration in seconds


class PodcastConfig(ObjectModel):
    table_name: ClassVar[str] = "podcast_config"
    name: str
    podcast_name: str
    podcast_tagline: str
    output_language: str = Field(default="English")
    person1_role: List[str]
    person2_role: List[str]
    conversation_style: List[str]
    engagement_technique: List[str]
    dialogue_structure: List[str]
    transcript_model: Optional[str] = None
    transcript_model_provider: Optional[str] = None
    user_instructions: Optional[str] = None
    ending_message: Optional[str] = None
    creativity: float = Field(ge=0, le=1)
    provider: str = Field(default="openai")
    voice1: str
    voice2: str
    model: str

    # Backwards compatibility
    @field_validator("person1_role", "person2_role", mode="before")
    @classmethod
    def split_string_to_list(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",")]
        return value

    @model_validator(mode="after")
    def validate_voices(self) -> "PodcastConfig":
        if not self.voice1 or not self.voice2:
            raise ValueError("Both voice1 and voice2 must be provided")
        return self

    def generate_episode(
        self,
        episode_name: str,
        text: str,
        instructions: str = "",
        longform: bool = False,
        chunks: int = 8,
        min_chunk_size=600,
    ):
        """Generate a podcast episode and save it to the database.
        
        Args:
            episode_name: Name of the episode
            text: Content to use for generating the podcast
            instructions: Additional instructions for the generation
            longform: Whether to generate a longer podcast
            chunks: Number of chunks for the podcast
            min_chunk_size: Minimum size of each chunk
            
        Returns:
            The path to the generated audio file
        """
        self.user_instructions = (
            instructions if instructions else self.user_instructions
        )
        conversation_config = {
            "max_num_chunks": chunks,
            "min_chunk_size": min_chunk_size,
            "conversation_style": self.conversation_style,
            "roles_person1": self.person1_role,
            "roles_person2": self.person2_role,
            "dialogue_structure": self.dialogue_structure,
            "podcast_name": self.podcast_name,
            "podcast_tagline": self.podcast_tagline,
            "output_language": self.output_language,
            "user_instructions": self.user_instructions,
            "engagement_techniques": self.engagement_technique,
            "creativity": self.creativity,
            "text_to_speech": {
                "output_directories": {
                    "transcripts": f"{DATA_FOLDER}/podcasts/transcripts",
                    "audio": f"{DATA_FOLDER}/podcasts/audio",
                },
                "temp_audio_dir": f"{DATA_FOLDER}/podcasts/audio/tmp",
                "ending_message": "Thank you for listening to this episode. Don't forget to subscribe to our podcast for more interesting conversations.",
                "default_tts_model": self.provider,
                self.provider: {
                    "default_voices": {
                        "question": self.voice1,
                        "answer": self.voice2,
                    },
                    "model": self.model,
                },
                "audio_format": "mp3",
            },
        }

        api_key_label = None
        llm_model_name = None
        tts_model = None

        if self.transcript_model_provider:
            if self.transcript_model_provider == "openai":
                api_key_label = "OPENAI_API_KEY"
                llm_model_name = self.transcript_model
            elif self.transcript_model_provider == "anthropic":
                api_key_label = "ANTHROPIC_API_KEY"
                llm_model_name = self.transcript_model
            elif self.transcript_model_provider == "gemini":
                api_key_label = "GOOGLE_API_KEY"
                llm_model_name = self.transcript_model

        # Use the default TTS model from Models page configuration
        # This respects user's TTS model selection instead of hardcoded mappings
        from open_notebook.domain.models import model_manager
        try:
            default_tts_model = model_manager.text_to_speech
            if default_tts_model:
                tts_model = f"{default_tts_model.provider}/{default_tts_model.models[0] if hasattr(default_tts_model, 'models') and default_tts_model.models else 'default'}"
            else:
                # Fallback to provider-based mapping if no default TTS model is set
                if self.provider == "google":
                    tts_model = "gemini"
                elif self.provider == "openai":
                    tts_model = "openai"
                elif self.provider == "anthropic":
                    tts_model = "anthropic"
                elif self.provider == "vertexai":
                    tts_model = "geminimulti"
                elif self.provider == "elevenlabs":
                    tts_model = "elevenlabs"
                else:
                    tts_model = "openai"  # Ultimate fallback
        except Exception as e:
            logger.warning(f"Failed to get default TTS model from Models page: {e}")
            # Fallback to provider-based mapping
            if self.provider == "google":
                tts_model = "gemini"
            elif self.provider == "openai":
                tts_model = "openai"
            elif self.provider == "anthropic":
                tts_model = "anthropic"
            elif self.provider == "vertexai":
                tts_model = "geminimulti"
            elif self.provider == "elevenlabs":
                tts_model = "elevenlabs"
            else:
                tts_model = "openai"  # Ultimate fallback

        logger.info(
            f"Generating episode {episode_name} with config {conversation_config} and using model {llm_model_name}, tts model {tts_model}"
        )

        try:
            # Generate the podcast audio file
            audio_file = generate_podcast(
                conversation_config=conversation_config,
                text=text,
                tts_model=tts_model,
                llm_model_name=llm_model_name,
                api_key_label=api_key_label,
                longform=longform,
            )
            
            # Only create the episode record if we successfully generated the audio
            if audio_file and os.path.exists(audio_file):
                audio_filename = os.path.basename(audio_file)
                # Find the corresponding transcript file (same hash, .txt extension)
                transcript_dir = os.path.join(DATA_FOLDER, "podcasts", "transcripts")
                transcript_filename = f"transcript_{audio_filename.replace('podcast_', '').replace('.mp3', '')}.txt"
                transcript_file = os.path.join(transcript_dir, transcript_filename)

                # Create the episode first to get the episode ID
                episode = PodcastEpisode(
                    name=episode_name,
                    template=self.id,  # Store template ID instead of name
                    instructions=instructions,
                    text=json.dumps(text) if not isinstance(text, str) else text,
                    audio_file=audio_file,
                    audio_url=f"/api/v1/podcasts/episodes/{episode_name}/audio"
                )
                episode.save()

                # Use the episode ID (without table prefix) for renaming
                # Handle both string IDs and RecordID objects
                if hasattr(episode.id, 'table_name') and hasattr(episode.id, 'record_id'):
                    # It's a RecordID object
                    episode_id = episode.id.record_id
                else:
                    # It's a string ID
                    episode_id = episode.id.split(":")[-1] if ":" in str(episode.id) else str(episode.id)
                new_audio_filename = f"podcast_{episode_id}.mp3"
                new_audio_file = os.path.join(DATA_FOLDER, "podcasts", "audio", new_audio_filename)
                new_audio_url = f"/data/podcasts/audio/{new_audio_filename}"
                new_transcript_filename = f"transcript_{episode_id}.txt"
                new_transcript_file = os.path.join(transcript_dir, new_transcript_filename)

                # Rename audio file
                if audio_file != new_audio_file:
                    os.rename(audio_file, new_audio_file)
                # Rename transcript file if it exists
                if os.path.exists(transcript_file) and transcript_file != new_transcript_file:
                    os.rename(transcript_file, new_transcript_file)

                # Re-encode audio to 128kbps, 44.1kHz, stereo using ffmpeg for browser compatibility
                try:
                    reencoded_file = audio_file + ".reencoded.mp3"
                    ffmpeg_cmd = [
                        "ffmpeg", "-y", "-i", audio_file,
                        "-ar", "44100", "-ac", "2", "-b:a", "128k",
                        reencoded_file
                    ]
                    subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    os.replace(reencoded_file, audio_file)
                except Exception as ffmpeg_err:
                    logger.error(f"FFmpeg re-encoding failed: {ffmpeg_err}")

                # Get audio duration using mutagen
                duration = None
                try:
                    audio = MP3(new_audio_file)
                    duration = audio.info.length
                except Exception as e:
                    logger.warning(f"Could not extract duration for {new_audio_file}: {e}")

                # Always set audio_url to the working API endpoint for playback using episode name
                episode.audio_url = f"/api/v1/podcasts/episodes/{episode.name}/audio"
                episode.audio_file = new_audio_file
                episode.status = "completed"
                episode.duration = duration
                episode.save()

                logger.info(f"Saved podcast episode: {episode_name} with audio file: {new_audio_file} and audio_url: {new_audio_url}")
                return new_audio_file
            else:
                logger.error(f"Failed to generate audio file for episode {episode_name}")
                # Create episode record with failed status
                episode = PodcastEpisode(
                    name=episode_name,
                    template=self.id,
                    instructions=instructions,
                    text=json.dumps(text) if not isinstance(text, str) else text,
                    audio_file="",
                    audio_url="",
                    status="failed"
                )
                episode.save()
                raise Exception(f"Failed to generate audio file for episode {episode_name}")
        except Exception as e:
            logger.error(f"Failed to generate episode {episode_name}: {e}")
            # Create episode record with failed status
            try:
                episode = PodcastEpisode(
                    name=episode_name,
                    template=self.id,
                    instructions=instructions,
                    text=json.dumps(text) if not isinstance(text, str) else text,
                    audio_file="",
                    audio_url="",
                    status="failed"
                )
                episode.save()
            except Exception as save_error:
                logger.error(f"Failed to save failed episode record: {save_error}")
            raise

    @field_validator(
        "name", "podcast_name", "podcast_tagline", "output_language", "model"
    )
    @classmethod
    def validate_required_strings(cls, value: str, field) -> str:
        if value is None or value.strip() == "":
            raise ValueError(f"{field.field_name} cannot be None or empty string")
        return value.strip()

    @field_validator("creativity")
    def validate_creativity(cls, value):
        if not 0 <= value <= 1:
            raise ValueError("Creativity must be between 0 and 1")
        return value


conversation_styles = [
    "Analytical",
    "Argumentative",
    "Informative",
    "Humorous",
    "Casual",
    "Formal",
    "Inspirational",
    "Debate-style",
    "Interview-style",
    "Storytelling",
    "Satirical",
    "Educational",
    "Philosophical",
    "Speculative",
    "Motivational",
    "Fun",
    "Technical",
    "Light-hearted",
    "Serious",
    "Investigative",
    "Debunking",
    "Didactic",
    "Thought-provoking",
    "Controversial",
    "Sarcastic",
    "Emotional",
    "Exploratory",
    "Fast-paced",
    "Slow-paced",
    "Introspective",
]

# Dialogue Structures
dialogue_structures = [
    "Topic Introduction",
    "Opening Monologue",
    "Guest Introduction",
    "Icebreakers",
    "Historical Context",
    "Defining Terms",
    "Problem Statement",
    "Overview of the Issue",
    "Deep Dive into Subtopics",
    "Pro Arguments",
    "Con Arguments",
    "Cross-examination",
    "Expert Interviews",
    "Case Studies",
    "Myth Busting",
    "Q&A Session",
    "Rapid-fire Questions",
    "Summary of Key Points",
    "Recap",
    "Key Takeaways",
    "Actionable Tips",
    "Call to Action",
    "Future Outlook",
    "Closing Remarks",
    "Resource Recommendations",
    "Trending Topics",
    "Closing Inspirational Quote",
    "Final Reflections",
]

# Podcast Participant Roles
participant_roles = [
    "Main Summarizer",
    "Questioner/Clarifier",
    "Optimist",
    "Skeptic",
    "Specialist",
    "Thesis Presenter",
    "Counterargument Provider",
    "Professor",
    "Student",
    "Moderator",
    "Host",
    "Co-host",
    "Expert Guest",
    "Novice",
    "Devil's Advocate",
    "Analyst",
    "Storyteller",
    "Fact-checker",
    "Comedian",
    "Interviewer",
    "Interviewee",
    "Historian",
    "Visionary",
    "Strategist",
    "Critic",
    "Enthusiast",
    "Mediator",
    "Commentator",
    "Researcher",
    "Reporter",
    "Advocate",
    "Debater",
    "Explorer",
]

# Engagement Techniques
engagement_techniques = [
    "Rhetorical Questions",
    "Anecdotes",
    "Analogies",
    "Humor",
    "Metaphors",
    "Storytelling",
    "Quizzes",
    "Personal Testimonials",
    "Quotes",
    "Jokes",
    "Emotional Appeals",
    "Provocative Statements",
    "Sarcasm",
    "Pop Culture References",
    "Thought Experiments",
    "Puzzles and Riddles",
    "Role-playing",
    "Debates",
    "Catchphrases",
    "Statistics and Facts",
    "Open-ended Questions",
    "Challenges to Assumptions",
    "Evoking Curiosity",
]