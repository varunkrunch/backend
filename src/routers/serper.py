# FastAPI Backend Serper Router

from fastapi import APIRouter, HTTPException, status, Query
from enum import Enum
from pydantic import Field
import requests
import os

# Create a router for Serper.dev Google search endpoints
router = APIRouter(
    prefix="/api/v1/serper",
    tags=["Serper Google Search"],
)

# Country Enum with flags and names as values
class Country(str, Enum):
    US = "🇺🇸 United States (us)"
    GB = "🇬🇧 United Kingdom (gb)" 
    CA = "🇨🇦 Canada (ca)"
    AU = "🇦🇺 Australia (au)"
    DE = "🇩🇪 Germany (de)"
    FR = "🇫🇷 France (fr)"
    ES = "🇪🇸 Spain (es)"
    IT = "🇮🇹 Italy (it)"
    JP = "🇯🇵 Japan (jp)"
    KR = "🇰🇷 South Korea (kr)"
    CN = "🇨🇳 China (cn)"
    IN = "🇮🇳 India (in)"
    BR = "🇧🇷 Brazil (br)"
    MX = "🇲🇽 Mexico (mx)"
    RU = "🇷🇺 Russia (ru)"
    NL = "🇳🇱 Netherlands (nl)"
    SE = "🇸🇪 Sweden (se)"
    NO = "🇳🇴 Norway (no)"
    DK = "🇩🇰 Denmark (dk)"
    FI = "🇫🇮 Finland (fi)"
    PL = "🇵🇱 Poland (pl)"
    CZ = "🇨🇿 Czech Republic (cz)"
    HU = "🇭🇺 Hungary (hu)"
    RO = "🇷🇴 Romania (ro)"
    BG = "🇧🇬 Bulgaria (bg)"
    HR = "🇭🇷 Croatia (hr)"
    SI = "🇸🇮 Slovenia (si)"
    SK = "🇸🇰 Slovakia (sk)"
    LT = "🇱🇹 Lithuania (lt)"
    LV = "🇱🇻 Latvia (lv)"
    EE = "🇪🇪 Estonia (ee)"
    IE = "🇮🇪 Ireland (ie)"
    PT = "🇵🇹 Portugal (pt)"
    GR = "🇬🇷 Greece (gr)"
    TR = "🇹🇷 Turkey (tr)"
    IL = "🇮🇱 Israel (il)"
    AE = "🇦🇪 UAE (ae)"
    SA = "🇸🇦 Saudi Arabia (sa)"
    EG = "🇪🇬 Egypt (eg)"
    ZA = "🇿🇦 South Africa (za)"
    NG = "🇳🇬 Nigeria (ng)"
    KE = "🇰🇪 Kenya (ke)"
    MA = "🇲🇦 Morocco (ma)"
    TN = "🇹🇳 Tunisia (tn)"
    
    def get_code(self) -> str:
        """Extract the country code from the enum value."""
        return self.value.split("(")[-1].rstrip(")")
    
    def get_name(self) -> str:
        """Extract the country name from the enum value."""
        return self.value.split(")")[0].split(" ", 1)[1]
    
    def get_flag(self) -> str:
        """Extract the flag from the enum value."""
        return self.value.split(" ")[0]

# Language Enum with flags and names as values
class Language(str, Enum):
    EN = "🇺🇸 English (en)"
    ES = "🇪🇸 Spanish (es)"
    FR = "🇫🇷 French (fr)"
    DE = "🇩🇪 German (de)"
    IT = "🇮🇹 Italian (it)"
    PT = "🇵🇹 Portuguese (pt)"
    RU = "🇷🇺 Russian (ru)"
    JA = "🇯🇵 Japanese (ja)"
    KO = "🇰🇷 Korean (ko)"
    ZH = "🇨🇳 Chinese (zh)"
    AR = "🇸🇦 Arabic (ar)"
    HI = "🇮🇳 Hindi (hi)"
    TH = "🇹🇭 Thai (th)"
    VI = "🇻🇳 Vietnamese (vi)"
    TR = "🇹🇷 Turkish (tr)"
    PL = "🇵🇱 Polish (pl)"
    NL = "🇳🇱 Dutch (nl)"
    SV = "🇸🇪 Swedish (sv)"
    DA = "🇩🇰 Danish (da)"
    NO = "🇳🇴 Norwegian (no)"
    FI = "🇫🇮 Finnish (fi)"
    CS = "🇨🇿 Czech (cs)"
    HU = "🇭🇺 Hungarian (hu)"
    RO = "🇷🇴 Romanian (ro)"
    BG = "🇧🇬 Bulgarian (bg)"
    HR = "🇭🇷 Croatian (hr)"
    SK = "🇸🇰 Slovak (sk)"
    SL = "🇸🇮 Slovenian (sl)"
    ET = "🇪🇪 Estonian (et)"
    LV = "🇱🇻 Latvian (lv)"
    LT = "🇱🇹 Lithuanian (lt)"
    EL = "🇬🇷 Greek (el)"
    HE = "🇮🇱 Hebrew (he)"
    FA = "🇮🇷 Persian (fa)"
    UR = "🇵🇰 Urdu (ur)"
    BN = "🇧🇩 Bengali (bn)"
    TA = "🇱🇰 Tamil (ta)"
    TE = "🇮🇳 Telugu (te)"
    ML = "🇮🇳 Malayalam (ml)"
    KN = "🇮🇳 Kannada (kn)"
    GU = "🇮🇳 Gujarati (gu)"
    PA = "🇮🇳 Punjabi (pa)"
    OR = "🇮🇳 Odia (or)"
    AS = "🇮🇳 Assamese (as)"
    NE = "🇳🇵 Nepali (ne)"
    SI = "🇱🇰 Sinhala (si)"
    MY = "🇲🇲 Burmese (my)"
    KM = "🇰🇭 Khmer (km)"
    LO = "🇱🇦 Lao (lo)"
    KA = "🇬🇪 Georgian (ka)"
    AM = "🇪🇹 Amharic (am)"
    TI = "🇪🇹 Tigrinya (ti)"
    SW = "🇹🇿 Swahili (sw)"
    ZU = "🇿🇦 Zulu (zu)"
    AF = "🇿🇦 Afrikaans (af)"
    SQ = "🇦🇱 Albanian (sq)"
    EU = "🇪🇸 Basque (eu)"
    BE = "🇧🇾 Belarusian (be)"
    BS = "🇧🇦 Bosnian (bs)"
    CA = "🇪🇸 Catalan (ca)"
    CY = "🇬🇧 Welsh (cy)"
    GL = "🇪🇸 Galician (gl)"
    IS = "🇮🇸 Icelandic (is)"
    MK = "🇲🇰 Macedonian (mk)"
    MT = "🇲🇹 Maltese (mt)"
    SR = "🇷🇸 Serbian (sr)"
    UK = "🇺🇦 Ukrainian (uk)"
    YI = "🇮🇱 Yiddish (yi)"
    
    def get_code(self) -> str:
        """Extract the language code from the enum value."""
        return self.value.split("(")[-1].rstrip(")")
    
    def get_name(self) -> str:
        """Extract the language name from the enum value."""
        return self.value.split(")")[0].split(" ", 1)[1]
    
    def get_flag(self) -> str:
        """Extract the flag from the enum value."""
        return self.value.split(" ")[0]

def get_serper_api_key() -> str:
    """Get Serper API key from environment variables."""
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Serper API key not configured. Please set SERPER_API_KEY environment variable."
        )
    return api_key

@router.get("/options")
async def get_search_options():
    """
    Get available countries and languages for search.
    
    Returns a list of all available countries and languages with their flags and names.
    """
    countries = [
        {
            "code": country.get_code(), 
            "name": country.get_name(), 
            "flag": country.get_flag(),
            "display": country.value
        }
        for country in Country
    ]
    
    languages = [
        {
            "code": language.get_code(), 
            "name": language.get_name(), 
            "flag": language.get_flag(),
            "display": language.value
        }
        for language in Language
    ]
    
    return {
        "countries": countries,
        "languages": languages,
        "total_countries": len(countries),
        "total_languages": len(languages)
    }

@router.get("/search")
async def google_search(
    query: str = Query(..., description="The search query string."),
    num_results: int = Query(10, description="Number of results to return (1-100)."),
    country: Country = Query(Country.US, description="Select country for search results. Use /api/v1/serper/options to see all available countries with flags."),
    language: Language = Query(Language.EN, description="Select language for search results. Use /api/v1/serper/options to see all available languages with flags.")
):
    """
    Google search using Serper.dev API.
    
    This endpoint automatically uses the SERPER_API_KEY from environment variables.
    No need to manually enter API key - it's loaded from .env file.
    """
    try:
        # Get API key from environment
        api_key = get_serper_api_key()
        
        # Prepare the request payload
        payload = {
            "q": query,
            "num": min(max(num_results, 1), 100),  # Clamp between 1 and 100
            "gl": country.get_code(),  # Get the country code from enum
            "hl": language.get_code()  # Get the language code from enum
        }
        
        # Make request to Serper.dev API
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            "https://google.serper.dev/search",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Serper API error: {response.status_code} - {response.text}"
            )
        
        data = response.json()
        
        # Return clean, simple response
        return {
            "query": query,
            "results": [
                {
                    "title": result.get("title", ""),
                    "link": result.get("link", ""),
                    "snippet": result.get("snippet", ""),
                    "position": i + 1
                }
                for i, result in enumerate(data.get("organic", []))
            ],
            "total_results": data.get("searchInformation", {}).get("totalResults"),
            "search_time": data.get("searchInformation", {}).get("searchTime")
        }
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to connect to Serper API: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )
