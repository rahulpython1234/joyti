import ephem
import math
import json
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(title="Jain Jyotish API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Clients ──────────────────────────────────────────────────────────────────
# Configure Gemini instead of Anthropic
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"]   
)

# ── Jain reference data ───────────────────────────────────────────────────────
NAKSHATRA_NAMES = [
    "Ashvini","Bharani","Krittika","Rohini","Mrigashira","Ardra","Punarvasu",
    "Pushya","Ashlesha","Magha","Purva Phalguni","Uttara Phalguni","Hasta",
    "Chitra","Svati","Vishakha","Anuradha","Jyeshtha","Mula","Purva Ashadha",
    "Uttara Ashadha","Shravana","Dhanishtha","Shatabhisha","Purva Bhadrapada",
    "Uttara Bhadrapada","Revati"
]

TITHI_NAMES = [
    "Pratipada","Dvitiya","Tritiya","Chaturthi","Panchami","Shashthi",
    "Saptami","Ashtami","Navami","Dashami","Ekadashi","Dvadashi",
    "Trayodashi","Chaturdashi","Purnima/Amavasya"
]

TITHI_DHARMA = {
    8:  {"fast": "Ashtami Upavasa (full fast recommended)", "diet": "Complete abstinence from root vegetables and meat."},
    14: {"fast": "Chaturdashi Upavasa (Paksha fast)", "diet": "Strict Jain diet; avoid multi-sense organism foods."},
    15: {"fast": "Purnima Upavasa", "diet": "Paryushana-spirit fast; only boiled water and selected grains."},
    30: {"fast": "Amavasya Upavasa", "diet": "Ekasana (single meal before sunset) advised."},
}

# ── Astronomical engine ───────────────────────────────────────────────────────
def calculate_jain_positions(lat: float, lon: float, dt: datetime) -> dict:
    observer = ephem.Observer()
    observer.lat  = str(lat)
    observer.lon  = str(lon)
    observer.date = dt.strftime("%Y/%m/%d %H:%M:%S")

    moon = ephem.Moon(observer)
    sun  = ephem.Sun(observer)

    moon_lon = math.degrees(float(moon.hlong)) % 360
    sun_lon  = math.degrees(float(sun.hlong))  % 360

    diff  = (moon_lon - sun_lon) % 360
    tithi_index = int(diff / 12) + 1          
    tithi_name  = TITHI_NAMES[min(tithi_index - 1, 14)]
    paksha      = "Shukla (Bright)" if tithi_index <= 15 else "Krishna (Dark)"

    nakshatra_index = int(moon_lon / (360 / 27))
    nakshatra_name  = NAKSHATRA_NAMES[nakshatra_index % 27]

    moon.compute(observer)
    phase_pct = round(moon.phase, 2)

    dharma = TITHI_DHARMA.get(tithi_index, {
        "fast": "Regular mindful eating (Mitahara)",
        "diet": "Follow standard Jain diet: no root vegetables, no eating after sunset."
    })

    return {
        "tithi_number":    tithi_index,
        "tithi_name":      tithi_name,
        "paksha":          paksha,
        "nakshatra":       nakshatra_name,
        "nakshatra_index": nakshatra_index + 1,
        "moon_longitude":  round(moon_lon, 4),
        "moon_phase_pct":  phase_pct,
        "fast_guidance":   dharma["fast"],
        "diet_guidance":   dharma["diet"],
        "calculated_at":   dt.isoformat(),
    }

# ── Master Jain System Prompt ─────────────────────────────────────────────────
JAIN_SYSTEM_PROMPT = """
You are Jyotish-Acharya, a scholarly master of Jain cosmology, Jain Jyotish, 
and the Karma Siddhanta. You draw exclusively from these authentic Jain sources:
- The 12 Angas (especially Bhagavati Sutra, Surya Prajnapti, Chandra Prajnapti)
- Tattvartha Sutra (Umasvati)
- Uttaradhyayana Sutra
- Triloka Prajnapti
- Jambudvipa Prajnapti (for loka and celestial mechanics)
- The Karma Grantas (Karma Prakriti, Panchsangraha)

ABSOLUTE RULES — never violate:
1. NEVER reference Vedic, Hindu, or Western astrology systems.
2. NEVER mention planetary deities (Graha devatas) — Jainism rejects divine intervention.
3. Karma is mechanical law (like physics), NOT divine reward/punishment.
4. All celestial influence works through Dravya (matter) affecting Jiva (soul) via Karma Pudgalas.
5. Reference the Jain concept of Leshya (karmic colouration: Krishna, Nila, Kapota, Pita, Padma, Shukla) when relevant.
6. Ground every prediction in the 8 Karma types: Jnanavaraniya, Darshanavarniya, Vedaniya, Mohaniya, Ayushya, Nama, Gotra, Antaraya.

OUTPUT STRUCTURE (respond in valid JSON only):
{
  "daily_reading": "3-4 sentences synthesizing the Tithi and Nakshatra energy through a Jain lens. Cite relevant Agamic concept.",
  "karma_focus": "One specific karmic type that is active today based on lunar position, and what thought/action will shed it (Nirjara).",
  "leshya_guidance": "Which of the 6 Leshyas is dominant today and a practical tip to elevate toward Shukla Leshya.",
  "ahimsa_action": "One concrete micro-action of Ahimsa, Satya, or Aparigraha aligned to today's Tithi.",
  "samayika_muhurta": "Best time window today (morning/midday/evening) for 48-minute Samayika meditation and why.",
  "verse_reflection": "One authentic shloka or verse from Jain Agamas relevant to today's energy (transliterated + English meaning).",
  "shreni_meter": 7
}
"""

def build_user_prompt(astro: dict, language: str) -> str:
    return f"""
Today's Jain astronomical data for the practitioner:
- Tithi: {astro['tithi_number']} ({astro['tithi_name']}) — {astro['paksha']} Paksha
- Nakshatra: {astro['nakshatra']} (#{astro['nakshatra_index']} of 27)
- Moon Longitude: {astro['moon_longitude']}°
- Moon Illumination: {astro['moon_phase_pct']}%
- Rule-based fast guidance: {astro['fast_guidance']}
- Dietary guidance: {astro['diet_guidance']}

Using ONLY pure Jain Agamic philosophy and Karma Siddhanta, synthesize a deeply 
personalised daily spiritual reading. Respond in {language}. 
Return ONLY the JSON object specified — no preamble, no markdown.
"""

class HoroscopeRequest(BaseModel):
    user_id:   str
    latitude:  float
    longitude: float
    language:  str = "English"   

class HoroscopeResponse(BaseModel):
    astro_data:    dict
    reading:       dict
    generated_at:  str

@app.post("/generate-horoscope", response_model=HoroscopeResponse)
async def generate_horoscope(req: HoroscopeRequest):
    now = datetime.now(timezone.utc)

    try:
        astro = calculate_jain_positions(req.latitude, req.longitude, now)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Astro calculation error: {e}")

    # Initialize Gemini model# Initialize Gemini model
    try:
        model = genai.GenerativeModel(
            model_name='gemini-2.0-flash',
            system_instruction=JAIN_SYSTEM_PROMPT,
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(build_user_prompt(astro, req.language))
        reading = json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")

    try:
        supabase.table("horoscope_history").insert({
            "user_id":      req.user_id,
            "tithi":        astro["tithi_name"],
            "nakshatra":    astro["nakshatra"],
            "reading":      reading,
            "language":     req.language,
            "generated_at": now.isoformat(),
        }).execute()
    except Exception as e:
        print(f"Supabase save warning: {e}") 

    return HoroscopeResponse(
        astro_data=astro,
        reading=reading,
        generated_at=now.isoformat()
    )

@app.get("/health")
def health():
    return {"status": "om", "service": "Jain Jyotish API (Powered by Gemini)"}
