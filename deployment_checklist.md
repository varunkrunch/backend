# 🚀 Models Page Deployment Checklist

## For Testing on Another Computer

### 📋 Prerequisites
- [ ] Node.js installed (for frontend)
- [ ] Python 3.8+ installed (for backend)
- [ ] SurrealDB installed and running
- [ ] Git (to clone repositories)

### 🔧 Backend Setup
1. **Clone and Setup Backend**
   ```bash
   git clone <your-repo>
   cd fastapi_backend
   pip install -r requirements.txt
   ```

2. **Environment Variables (.env file)**
   ```bash
   # Required API Keys (add the ones you want to use)
   OPENAI_API_KEY=your_openai_key_here
   THEALPHA_API_KEY=your_thealpha_key_here
   ANTHROPIC_API_KEY=your_anthropic_key_here
   GROQ_API_KEY=your_groq_key_here
   MISTRAL_API_KEY=your_mistral_key_here
   DEEPSEEK_API_KEY=your_deepseek_key_here
   
   # Optional API Keys
   GOOGLE_API_KEY=your_google_key_here
   PALM_API_KEY=your_palm_key_here
   ELEVENLABS_API_KEY=your_elevenlabs_key_here
   VOYAGE_API_KEY=your_voyage_key_here
   XAI_API_KEY=your_xai_key_here
   
   # Database Configuration
   SURREALDB_URL=ws://localhost:8000/rpc
   SURREALDB_NAMESPACE=fastapi_backend
   SURREALDB_DATABASE=fastapi_backend
   SURREALDB_USER=root
   SURREALDB_PASS=root
   ```

3. **Start SurrealDB**
   ```bash
   surreal start --log trace --user root --pass root memory
   ```

4. **Start Backend**
   ```bash
   cd fastapi_backend
   python run.py
   ```
   - Backend should start on `http://localhost:8001`
   - Health check: `http://localhost:8001/health`

### 🎨 Frontend Setup
1. **Clone and Setup Frontend**
   ```bash
   cd frontend-connector
   npm install
   ```

2. **Start Frontend**
   ```bash
   npm run dev
   ```
   - Frontend should start on `http://localhost:3000`
   - Navigate to `http://localhost:3000/settings`

### 🔍 Initial Configuration
1. **Open Models Page**
   - Go to `http://localhost:3000/settings`
   - Click on "Models" tab

2. **Add Models** (for each type you want to use)
   - **Language Models**: Add at least one (e.g., `openai/gpt-4o-mini`)
   - **Embedding Models**: Add at least one (e.g., `openai/text-embedding-3-small`)
   - **TTS Models**: Add at least one (e.g., `openai/gpt-4o-mini-tts`)
   - **STT Models**: Add at least one (e.g., `openai/whisper-1`)

3. **Set Default Models**
   - Select default models for each type
   - Click "Save Defaults" button in each section

### ✅ Verification
1. **Check Models API**
   ```bash
   curl http://localhost:8001/api/v1/models
   ```
   - Should return list of configured models

2. **Check Defaults API**
   ```bash
   curl http://localhost:8001/api/v1/models/config/defaults
   ```
   - Should return default model IDs

3. **Test Chat Functionality**
   - Try using the chat feature
   - Should use the configured default models

### 🚨 Common Issues & Solutions

#### Issue: "No providers available"
- **Cause**: No API keys configured
- **Solution**: Add API keys to `.env` file and restart backend

#### Issue: "Model not found"
- **Cause**: No models added yet
- **Solution**: Add models through the frontend interface

#### Issue: "API key not found"
- **Cause**: Environment variable not set
- **Solution**: Check `.env` file and restart backend

#### Issue: "Database connection failed"
- **Cause**: SurrealDB not running
- **Solution**: Start SurrealDB server

#### Issue: "Frontend can't connect to backend"
- **Cause**: Backend not running or wrong port
- **Solution**: Ensure backend is running on port 8001

### 📊 Expected Initial State
- **Models**: Empty (0 models configured)
- **Defaults**: All null/empty
- **Providers**: Only those with API keys in `.env`
- **Status**: Ready for user to add models and configure

### 🔄 Migration from Current Setup
If you want to copy your current configuration:

1. **Export Current Models**
   ```bash
   curl http://localhost:8001/api/v1/models > models_backup.json
   ```

2. **Export Current Defaults**
   ```bash
   curl http://localhost:8001/api/v1/models/config/defaults > defaults_backup.json
   ```

3. **Copy .env file** to new computer

4. **Import Models** (you'll need to create import scripts)

### 🎯 Key Points
- **API Keys**: Only providers with API keys will appear in dropdowns
- **Models**: Must be added through frontend interface
- **Defaults**: Must be set and saved for each model type
- **Database**: Starts empty, populated by user actions
- **No Migration**: Fresh install starts with clean slate

