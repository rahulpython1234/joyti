import ephem
import math
import json
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

# ─── MASTER AI TOGGLE ─────────────────────────────────────────────────────────
# Set to True when Anthropic/Claude quota is restored. False = deterministic engine only.
USE_AI = False

app = FastAPI(title="Jain Jyotish API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── AI client — gated by USE_AI ───────────────────────────────────────────────
# Original: from anthropic import Anthropic / anthropic_client = Anthropic(...)
# Wrapped so the anthropic package is not required when USE_AI = False.
if USE_AI:
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
else:
    anthropic_client = None

# ── Supabase client ───────────────────────────────────────────────────────────
supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_KEY"],
)

# ── Jain reference data ───────────────────────────────────────────────────────
NAKSHATRA_NAMES = [
    "Ashvini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Svati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishtha", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada",
    "Revati",
]

TITHI_NAMES = [
    "Pratipada", "Dvitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dvadashi",
    "Trayodashi", "Chaturdashi", "Purnima/Amavasya",
]

# Jain fasting/dietary rules keyed by tithi number (1–30)
TITHI_DHARMA = {
    8:  {"fast": "Ashtami Upavasa (full fast recommended)",
         "diet": "Complete abstinence from root vegetables and meat."},
    14: {"fast": "Chaturdashi Upavasa (Paksha fast)",
         "diet": "Strict Jain diet; avoid multi-sense organism foods."},
    15: {"fast": "Purnima Upavasa",
         "diet": "Paryushana-spirit fast; only boiled water and selected grains."},
    30: {"fast": "Amavasya Upavasa",
         "diet": "Ekasana (single meal before sunset) advised."},
}

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — NAKSHATRA_DATA
# 27 entries keyed by nakshatra name matching NAKSHATRA_NAMES above.
# Fields: karma_type, leshya, base_energy, nirjara_path, verse_key
# ═══════════════════════════════════════════════════════════════════════════════
NAKSHATRA_DATA = {
    "Ashvini": {
        "karma_type": "Ayushya",
        "leshya": "Padma",
        "base_energy": (
            "Ashvini activates Ayushya Karma — the Pudgala configuration that "
            "delimits the Jiva's present Paryaya (mode of existence). As the "
            "Surya Prajnapti delineates, the soul's sojourn in its current "
            "body-field is drawn tight by these accumulated karmic particles; "
            "their ripening sets the boundary of this incarnation. Under "
            "Ashvini's field, the practitioner is called to perceive the "
            "impermanence of the current Dravya-form without reactive Raga or "
            "Dvesha, recognising the Jiva's eternity beyond every Paryaya."
        ),
        "nirjara_path": (
            "Kayotsarga — standing body-abandonment meditation for 12 minutes "
            "at dawn, releasing identification with the physical Dravya and "
            "resting in pure Jiva-consciousness"
        ),
        "verse_key": "TS_10_1",
    },
    "Bharani": {
        "karma_type": "Mohaniya",
        "leshya": "Krishna",
        "base_energy": (
            "Bharani pulses with Mohaniya Karma — the most tenacious of the "
            "eight Karma types, which deludes the Jiva into mistaking the "
            "non-self (Ajiva) for the self. The Karma Prakriti describes "
            "Mohaniya as binding through the four Kashayas: anger, pride, "
            "deceit, and greed — each amplified when the Jiva acts under this "
            "star's intense gravitational field without Viveka. Krishna Leshya "
            "deepens the pull; even subtle reactive impulses bind dense "
            "Pudgalas today."
        ),
        "nirjara_path": (
            "Pratikraman at dusk — a formal verbal and mental confession of the "
            "day's Kashayas, naming each transgression against Ahimsa and the "
            "five Anuvratas before requesting forgiveness from all beings"
        ),
        "verse_key": "US_29_7",
    },
    "Krittika": {
        "karma_type": "Vedaniya",
        "leshya": "Pita",
        "base_energy": (
            "Under Krittika's sharp domain, Vedaniya Karma — the karma that "
            "produces pleasure and pain experiences — ripens with particular "
            "intensity. The Bhagavati Sutra establishes that Sukha and Duhkha "
            "are not external events but the precise fruition of Pudgalas "
            "previously bound through Raga and Dvesha. Krittika calls the "
            "practitioner to witness sensation as the passing of old karma "
            "rather than a present cause for new reactive binding."
        ),
        "nirjara_path": (
            "Svadhyaya — study one chapter of the Uttaradhyayana Sutra on the "
            "mechanics of Vedaniya Karma, transmuting intellectual understanding "
            "into Samyak-Jnana that dissolves the Pudgala veil"
        ),
        "verse_key": "TS_8_2",
    },
    "Rohini": {
        "karma_type": "Nama",
        "leshya": "Padma",
        "base_energy": (
            "Rohini activates Nama Karma — the vast category of Pudgalas that "
            "determine the soul's current manifestation: its senses, faculties, "
            "beauty, and the Dravya-composition of the entire body-field. The "
            "Jambudvipa Prajnapti speaks of the cosmos as a karmic loom on "
            "which each Paryaya is woven; Rohini is the moment the weaving "
            "becomes visible in form. Today, the practitioner is invited to "
            "regard the body not as the Jiva but as an instrument constructed "
            "by Nama Pudgalas for the purpose of practice."
        ),
        "nirjara_path": (
            "Samayika — a full 48-minute session of equanimity practice, sitting "
            "in complete stillness, withdrawing identification from all Nama "
            "qualities through Yoga-nirodha (restraint of body, speech, and mind)"
        ),
        "verse_key": "NS_1_3",
    },
    "Mrigashira": {
        "karma_type": "Jnanavaraniya",
        "leshya": "Pita",
        "base_energy": (
            "Mrigashira resonates with Jnanavaraniya Karma — the Pudgalas that "
            "veil the soul's infinite knowledge (Ananta-Jnana). The Tattvartha "
            "Sutra establishes that the Jiva's inherent nature is omniscience; "
            "these karmic particles function as a screen producing the illusion "
            "of partial, limited cognition. The deer-star teaches that searching "
            "outward for knowledge deepens the veil; turning inward toward "
            "Atma-swaroop through Anupreksha (reflection) dissolves it."
        ),
        "nirjara_path": (
            "Namokar Mantra recitation — 108 repetitions at sunrise on a tulsi "
            "mala, focusing awareness on the Pancha-Paramesthi whose Kevala-Jnana "
            "represents the fully unveiled soul-state toward which the practitioner moves"
        ),
        "verse_key": "TS_1_4",
    },
    "Ardra": {
        "karma_type": "Darshanavarniya",
        "leshya": "Nila",
        "base_energy": (
            "Ardra activates Darshanavarniya Karma — Pudgalas that cloud the "
            "soul's intrinsic right perception (Samyak-Darshana). The Karma "
            "Prakriti describes this karma as obscuring not specific facts but "
            "the fundamental capacity for clear spiritual vision — the direct "
            "perception of the Jiva as eternally distinct from Ajiva. Under "
            "Ardra's turbulent field, confusion about the nature of reality "
            "intensifies; this is not a defect but a signal to redirect the "
            "Drashti toward Nishchaya-Naya (ultimate standpoint)."
        ),
        "nirjara_path": (
            "Vandana — formal reverential salutation to the Arihanta, "
            "re-orienting the Darshana faculty toward its proper object: "
            "the liberated soul as living mirror of the practitioner's own true nature"
        ),
        "verse_key": "US_28_14",
    },
    "Punarvasu": {
        "karma_type": "Antaraya",
        "leshya": "Padma",
        "base_energy": (
            "Punarvasu carries the energy of Antaraya Karma — the Pudgalas that "
            "obstruct the soul's natural capacities of giving (Dana-Antaraya), "
            "receiving (Labha-Antaraya), enjoyment (Bhoga-Antaraya), continuous "
            "enjoyment (Upabhoga-Antaraya), and spiritual energy (Virya-Antaraya). "
            "The Panchsangraha notes that Antaraya creates the felt sense of "
            "blockage: a practitioner capable of great generosity may find "
            "obstructions arising. Punarvasu signals these obstacles are karmic "
            "configurations ready to be shed through direct counter-action."
        ),
        "nirjara_path": (
            "Dana practice — perform one act of genuine, ego-free giving today "
            "whether of food, time, knowledge, or comfort, as the direct "
            "antidote to Dana-Antaraya Karma through Bhava-Shuddhi (purity of intention)"
        ),
        "verse_key": "TS_9_3",
    },
    "Pushya": {
        "karma_type": "Ayushya",
        "leshya": "Shukla",
        "base_energy": (
            "Pushya — the most auspicious Nakshatra in Jain cosmological "
            "reckoning — activates Ayushya Karma in its most refined mode: "
            "the karma governing the duration of a spiritually fertile human "
            "birth. The Chandra Prajnapti identifies Pushya as a lunar mansion "
            "of exceptional Pudgala-purity where the subtle body receives "
            "minimal new karmic influx naturally. Shukla Leshya prevails: the "
            "Jiva rests in a field of reduced Asrava, making every spiritual "
            "act performed today carry exponentially amplified Nirjara power."
        ),
        "nirjara_path": (
            "Full 48-minute Samayika in Shukla Dhyana (pure, object-free "
            "meditation), holding Atma-swaroop as the sole object — today's "
            "Nirjara is direct and powerful; do not waste this Nakshatra"
        ),
        "verse_key": "SS_1_1",
    },
    "Ashlesha": {
        "karma_type": "Mohaniya",
        "leshya": "Kapota",
        "base_energy": (
            "Ashlesha intensifies Mohaniya Karma through the Kashaya of Maya "
            "(deceit) — one of the four root passions of the Karma Prakriti. "
            "Kapota (grey) Leshya is particularly active: the Jiva may "
            "rationalise Adharma as Dharma, or mistake partial understanding "
            "for Samyak-Jnana. The Bhagavati Sutra cautions that Maya-Mohaniya "
            "is the subtlest form of self-deception, binding the soul in the "
            "finest Karma Pudgalas that are precisely the hardest to perceive "
            "and therefore the hardest to shed."
        ),
        "nirjara_path": (
            "Satya Anuvrata — a formal vow of complete truthfulness in speech "
            "and thought for this entire day, as the direct antidote to "
            "Maya-Kashaya; include written reflection on three instances where "
            "Maya arose subtly in the past week"
        ),
        "verse_key": "US_29_14",
    },
    "Magha": {
        "karma_type": "Gotra",
        "leshya": "Krishna",
        "base_energy": (
            "Magha activates Gotra Karma — the subtle Pudgalas determining the "
            "soul's social and spiritual status-field in its current "
            "manifestation. The Tattvartha Sutra describes Uchcha-Gotra (high "
            "status karma) and Nichha-Gotra (lowering karma) as the two sub- "
            "types. Magha, connected in Jain cosmology to ancestral karma "
            "patterns and the concept of lineage, calls the practitioner to "
            "examine Mana-Kashaya (pride) and its subtle role in binding Gotra "
            "Pudgalas through status-seeking, hierarchy-protection, and the "
            "quiet cruelty of condescension."
        ),
        "nirjara_path": (
            "Pratikraman with specific focus on Mana (pride) — reviewing the "
            "past day for every moment the ego-self sought recognition or "
            "resisted humility, then formally releasing each instance through "
            "spoken or silent Kshamapana (request for forgiveness)"
        ),
        "verse_key": "TS_6_1",
    },
    "Purva Phalguni": {
        "karma_type": "Vedaniya",
        "leshya": "Nila",
        "base_energy": (
            "Purva Phalguni activates the pleasant dimension of Vedaniya Karma "
            "— Sata-Vedaniya Pudgalas are particularly active, creating a pull "
            "toward sensory enjoyment and Bhoga. The Dasavaikalika Sutra warns "
            "that unchecked pleasure-seeking under this Nakshatra's field binds "
            "fresh Vedaniya Pudgalas through Bhoga-Parigraha (indulgence in "
            "sense pleasures), extending the cycle of return to experience "
            "their fruit in a future birth. Even legitimate pleasure enjoyed "
            "with attachment becomes a binding agent today."
        ),
        "nirjara_path": (
            "Aparigraha Anuvrata — define a conscious limit of consumption: "
            "eat only what is necessary, acquire nothing beyond what was already "
            "planned, and withdraw one sense organ from its accustomed stimulus "
            "for a minimum of two hours"
        ),
        "verse_key": "DV_4_8",
    },
    "Uttara Phalguni": {
        "karma_type": "Nama",
        "leshya": "Shukla",
        "base_energy": (
            "Uttara Phalguni refines Nama Karma through Shubha-Nama — the "
            "auspicious body-karma configurations producing birth in a Kshetra "
            "conducive to Dharma practice. The Triloka Prajnapti describes how "
            "certain Nakshatras accelerate the ripening of previously "
            "accumulated Shubha-Pudgalas, creating a window where external "
            "conditions align with the soul's inner Dharma-capacity. Shukla "
            "Leshya prevails: this is a day when practice converts to Nirjara "
            "at an elevated rate."
        ),
        "nirjara_path": (
            "Svadhyaya followed by Samayika — study one Sutra from the "
            "Tattvartha Sutra and then sit in equanimity for 48 minutes, "
            "allowing intellectual understanding to settle into direct "
            "Anubhava (lived experience) of the soul's purity"
        ),
        "verse_key": "NS_1_10",
    },
    "Hasta": {
        "karma_type": "Jnanavaraniya",
        "leshya": "Pita",
        "base_energy": (
            "Hasta activates all five sub-categories of Jnanavaraniya Karma "
            "simultaneously: Mati-Jnana (sensory knowing), Shruta-Jnana "
            "(scriptural knowing), Avadhi-Jnana (clairvoyance), Manah-Paryaya- "
            "Jnana (mind-reading), and Kevala-Jnana (omniscience) — each veiled "
            "by a corresponding Pudgala layer. The Panchsangraha notes that "
            "Hasta marks a day when the effort to pierce one veil through "
            "concentrated Svadhyaya generates momentum that weakens all five "
            "simultaneously."
        ),
        "nirjara_path": (
            "Two hours of uninterrupted Svadhyaya with written reflection on "
            "the Pancha-Jnana doctrine from the Tattvartha Sutra — converting "
            "intellectual understanding into Samyak-Jnana through deliberate "
            "contemplative reading rather than passive study"
        ),
        "verse_key": "TS_1_1",
    },
    "Chitra": {
        "karma_type": "Darshanavarniya",
        "leshya": "Padma",
        "base_energy": (
            "Chitra — the star of brilliance and luminous form — paradoxically "
            "activates Darshanavarniya Karma: the veiling of the soul's innate "
            "Samyak-Darshana. The Karma Prakriti identifies four Nidra sub-types "
            "(sleep-states of the perception faculty) within Darshanavarniya; "
            "under Chitra's luminous phenomenal field, these sleepings of the "
            "Darshana faculty may intensify through the very brilliance of the "
            "world drawing the Jiva's attention outward rather than inward "
            "toward its witness nature."
        ),
        "nirjara_path": (
            "Pratikraman at dawn focusing specifically on Mithya-Darshana "
            "(wrong perception) in subtle forms: attachment to the body as self, "
            "aversion toward any being, and the quiet conceit of believing "
            "spiritual progress has been made"
        ),
        "verse_key": "SS_1_4",
    },
    "Svati": {
        "karma_type": "Antaraya",
        "leshya": "Pita",
        "base_energy": (
            "Svati — the independent wind-star — resonates with Virya-Antaraya: "
            "the obstruction of the soul's inherent infinite energy (Ananta- "
            "Virya). The Tattvartha Sutra establishes infinite energy as the "
            "soul's natural state; Antaraya Pudgalas function as friction "
            "against this energy, producing spiritual fatigue, inability to "
            "begin practices, and procrastination in Dharma. Under Svati, the "
            "Pita Leshya's threshold momentum means these obstructions are "
            "particularly moveable with directed effort."
        ),
        "nirjara_path": (
            "Begin a practice that has been postponed — even five minutes of "
            "Kayotsarga performed despite reluctance directly targets "
            "Virya-Antaraya, as the soul's energy asserts itself against the "
            "Pudgala obstruction through sheer act of will (Purushaartha)"
        ),
        "verse_key": "TS_9_1",
    },
    "Vishakha": {
        "karma_type": "Mohaniya",
        "leshya": "Kapota",
        "base_energy": (
            "Vishakha activates Mohaniya Karma through Krodha-Kashaya — the "
            "anger-passion that binds the densest grades of Karma Pudgalas. "
            "The Uttaradhyayana Sutra records that a single moment of "
            "unconquered anger can bind karmas requiring many Antaras (cosmic "
            "time-units) to shed. Vishakha's two-headed forked nature in Jain "
            "cosmology reflects the choice-point: the Jiva can act from Krodha "
            "and bind new Pudgalas, or witness the arising in Samabhava "
            "(equanimity) and shed existing ones."
        ),
        "nirjara_path": (
            "Mauna Vrata — maintain complete silence for two full hours, "
            "specifically during the period when you feel the strongest pull "
            "toward reactive speech; this Kayotsarga of the Vak-Yoga (speech "
            "faculty) directly arrests Krodha-Kashaya at its point of expression"
        ),
        "verse_key": "US_29_21",
    },
    "Anuradha": {
        "karma_type": "Ayushya",
        "leshya": "Padma",
        "base_energy": (
            "Anuradha — the star of devotion and right relationship — activates "
            "Ayushya Karma in its most conscious dimension: the recognition that "
            "this human Paryaya is finite, spiritually precious, and specifically "
            "configured for Moksha-progression. The Chandra Prajnapti notes that "
            "the human Jiva possesses all five senses plus the Sanjni capacity "
            "(rational mind) — making this birth the supreme opportunity in the "
            "karmic cycle. Anuradha calls the practitioner to renew commitment "
            "to the Dharma-opportunity this birth represents."
        ),
        "nirjara_path": (
            "Panchanuvrata renewal — verbally or mentally reaffirm your five "
            "small vows (Ahimsa, Satya, Asteya, Brahmacharya, Aparigraha) and "
            "identify one specific instance where each was tested in the past "
            "week; resolve one area of Anuvrata weakness concretely"
        ),
        "verse_key": "TS_10_1",
    },
    "Jyeshtha": {
        "karma_type": "Gotra",
        "leshya": "Kapota",
        "base_energy": (
            "Jyeshtha — the eldest, the chief — carries the weight of "
            "Uchcha-Gotra Karma at its most ambivalent: accumulated Pudgalas "
            "of status, seniority, and hierarchical position. The Karma Grantas "
            "warn that Uchcha-Gotra unexamined breeds Mana-Kashaya (pride) "
            "which immediately binds fresh layers of Gotra and Mohaniya karma "
            "in a self-reinforcing cycle. Kapota Leshya deepens the confusion: "
            "the practitioner may genuinely believe that spiritual seniority "
            "exempts them from Vinaya (humility practice)."
        ),
        "nirjara_path": (
            "One act of Vinaya toward someone you consider junior, less "
            "qualified, or of lower social position — without inner condescension. "
            "This Bhava-Shuddhi (purification of attitude) directly sheds "
            "Uchcha-Gotra Pudgalas accumulated through habitual hierarchy"
        ),
        "verse_key": "US_28_29",
    },
    "Mula": {
        "karma_type": "Mohaniya",
        "leshya": "Krishna",
        "base_energy": (
            "Mula — the root and the uprooting — resonates with the most "
            "fundamental dimension of Mohaniya Karma: Darshana-Mohaniya, the "
            "perception-deluding karma that produces Mithya-Drashti (wrong "
            "view) at the deepest level of the Jiva's orientation. Kundakunda's "
            "Niyamasara identifies this karma as the primary obstacle to "
            "Samyak-Darshana — the foundational right view that Jiva and Ajiva "
            "are eternally distinct. Krishna Leshya and Mula together mark a "
            "day for radical ontological examination of what the Jiva takes to "
            "be its self."
        ),
        "nirjara_path": (
            "Kayotsarga in Khadgasana (standing posture) for 20 minutes, "
            "followed by contemplation of the Jiva-Ajiva distinction from "
            "Tattvartha Sutra 2.1 — using the body's complete stillness as "
            "direct lived evidence of the soul's radical separateness from matter"
        ),
        "verse_key": "NS_1_8",
    },
    "Purva Ashadha": {
        "karma_type": "Vedaniya",
        "leshya": "Nila",
        "base_energy": (
            "Purva Ashadha activates Asata-Vedaniya — the unpleasant-feeling "
            "dimension of Vedaniya Karma — Pudgalas producing experiences of "
            "suffering, discomfort, and difficulty. The Bhagavati Sutra "
            "establishes that these experiences are not external events but the "
            "precise fruition of previously bound Pudgalas attracted through "
            "Dvesha and violent mental activity. Under this Nakshatra, apparent "
            "hardship is literally old karma departing the Jiva's field — a "
            "cause for equanimity rather than reactive new binding."
        ),
        "nirjara_path": (
            "Titiksha (patient endurance) — consciously receive one "
            "uncomfortable sensation, emotion, or situation today without "
            "attempting to escape, fix, or assign blame, simply remaining "
            "present as the witnessing Jiva and allowing the Pudgala to pass"
        ),
        "verse_key": "TS_8_14",
    },
    "Uttara Ashadha": {
        "karma_type": "Nama",
        "leshya": "Shukla",
        "base_energy": (
            "Uttara Ashadha — the star of final victory and cosmic order — "
            "activates the most auspicious sub-categories of Nama Karma: the "
            "Shubha-Nama Pudgalas producing a spiritually capable body and a "
            "social context conducive to liberation. The Jambudvipa Prajnapti "
            "identifies Uttara Ashadha as a Nakshatra of cosmic culmination; "
            "Shukla Leshya prevails in its field. Today, every act of Dharma "
            "is amplified by the field's purity — no practice performed with "
            "Samyak-Bhava (right intention) is wasted."
        ),
        "nirjara_path": (
            "Trikala Samayika — perform Samayika three times at dawn, midday, "
            "and dusk, recognising that Uttara Ashadha's field makes each "
            "session carry extraordinary Nirjara power; do not neglect this "
            "rare alignment"
        ),
        "verse_key": "US_29_14",
    },
    "Shravana": {
        "karma_type": "Jnanavaraniya",
        "leshya": "Pita",
        "base_energy": (
            "Shravana — the star of listening and transmission — resonates with "
            "Shruta-Jnana-Avarana: the specific veil over scriptural and "
            "transmitted knowledge. The Dasavaikalika Sutra places Shruta-Dharma "
            "(the Dharma of hearing authentic teaching) as the second of the "
            "four pillars of Agamic life. Under Shravana, the practitioner who "
            "listens deeply to authentic Agamic teaching receives maximal "
            "reduction of Jnanavaraniya Pudgalas — the act of genuine, "
            "attentive hearing itself becomes the Nirjara."
        ),
        "nirjara_path": (
            "Listen to one recitation or reading of authentic Jain Agamic text "
            "today with complete, undivided attention — even 15 minutes of "
            "genuine Shruta-Dharma practice under Shravana Nakshatra carries "
            "unusual Nirjara power for Jnanavaraniya Karma"
        ),
        "verse_key": "DV_1_1",
    },
    "Dhanishtha": {
        "karma_type": "Antaraya",
        "leshya": "Pita",
        "base_energy": (
            "Dhanishtha — the star of abundance and percussion — activates "
            "Bhoga-Antaraya and Upabhoga-Antaraya: the obstruction of the "
            "soul's capacity to fully enjoy the fruits of its own Dharma effort. "
            "The Panchsangraha notes the subtle cruelty of this karma: the "
            "practitioner receives the opportunity but finds it blocked, or "
            "acquires what was sought but cannot fully receive it. Under "
            "Dhanishtha, these interruptions are recognised as outgoing karma, "
            "not obstacles from outside."
        ),
        "nirjara_path": (
            "Dana-Vrata — commit to giving away one material object of genuine "
            "value before sunset, approaching the relinquishment as the soul's "
            "freedom from Pudgala, directly countering Bhoga-Antaraya through "
            "the Tyaga (renunciation) that demonstrates the Jiva's true richness"
        ),
        "verse_key": "TS_9_7",
    },
    "Shatabhisha": {
        "karma_type": "Darshanavarniya",
        "leshya": "Kapota",
        "base_energy": (
            "Shatabhisha — the hundred physicians, the healing star — carries "
            "Darshanavarniya Karma in its Nidra sub-category: the Pudgalas "
            "producing spiritual torpor and the Jiva's habitual tendency to "
            "fall unconscious in its witnessing capacity. The Karma Prakriti "
            "identifies five grades of Nidra from light drowsiness to deep "
            "spiritual unconsciousness; Shatabhisha's field makes the practitioner "
            "particularly prone to the middle grades of this veiling of clear "
            "Darshana."
        ),
        "nirjara_path": (
            "Jagaran — deliberate spiritual wakefulness: sit for 30 minutes "
            "before your usual sleep time in alert, non-conceptual awareness, "
            "actively resisting Nidra's pull as a conscious act of "
            "Darshanavarniya Nirjara through the assertion of pure witnessing"
        ),
        "verse_key": "US_29_3",
    },
    "Purva Bhadrapada": {
        "karma_type": "Mohaniya",
        "leshya": "Nila",
        "base_energy": (
            "Purva Bhadrapada resonates with the Lobha-Kashaya (greed-passion) "
            "dimension of Mohaniya Karma — the subtlest and most tenacious of "
            "the four root passions. The Uttaradhyayana Sutra notes that Lobha "
            "persists even in the practitioner who has subdued anger, pride, "
            "and deceit, manifesting as subtle acquisitiveness, spiritual "
            "achievement-hoarding, and the quiet accumulation of comfort and "
            "security. Under this Nakshatra, even subtle Parigraha (inner "
            "possessiveness) binds powerful Karma Pudgalas."
        ),
        "nirjara_path": (
            "Aparigraha audit — make a written or mental list of everything "
            "currently held beyond genuine need; select one item and release it "
            "before sunset, approaching the relinquishment as the Jiva "
            "exercising its natural freedom from Pudgala-attachment"
        ),
        "verse_key": "US_28_34",
    },
    "Uttara Bhadrapada": {
        "karma_type": "Gotra",
        "leshya": "Shukla",
        "base_energy": (
            "Uttara Bhadrapada — the deep, stable water-star — activates Gotra "
            "Karma in its most refined configuration: Nichha-Gotra, the humbling "
            "karma producing circumstances of simplicity and reduced social "
            "recognition. Kundakunda's Niyamasara presents Nichha-Gotra not as "
            "karmic punishment but as the karma of a Jiva that has previously "
            "practised genuine Vinaya and chosen Dharma over status. Under "
            "Uttara Bhadrapada's Shukla field, reduced visibility in the world "
            "is a marker of spiritual acceleration."
        ),
        "nirjara_path": (
            "Complete all of today's activities without seeking recognition, "
            "feedback, or appreciation from any external source — perform all "
            "Dharma actions in inner silence, renouncing even the subtle Mana "
            "of spiritual achievement and the quiet craving for acknowledgment"
        ),
        "verse_key": "SS_1_7",
    },
    "Revati": {
        "karma_type": "Ayushya",
        "leshya": "Padma",
        "base_energy": (
            "Revati — the last of the 27, the star of completion and cosmic "
            "return — activates Ayushya Karma at the junction of cycles: the "
            "moment when one Paryaya approaches completion and the next begins "
            "to be configured by present karma. The Surya Prajnapti describes "
            "Revati as the point where the cosmic loom rests before beginning "
            "a new weave. For the practitioner, Revati marks a day of honest "
            "karmic accounting: what has been shed in this cycle, and what "
            "Pudgalas are now crystallising for the next?"
        ),
        "nirjara_path": (
            "Paryushana-spirit Pratikraman — reflect on the current lunar cycle "
            "as a whole: which Anuvrata was upheld, which was broken, which "
            "karma was consciously shed, which was newly bound; offer "
            "Kshamapana to all beings across all six realms, even in thought alone"
        ),
        "verse_key": "TS_10_7",
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — TITHI_MODIFIER
# 15 entries keyed by integer 1–15. Krishna paksha tithis 16–30 are normalised
# to 1–15 by the engine formula: tithi_key = 30 - tithi_number + 1
# ═══════════════════════════════════════════════════════════════════════════════
TITHI_MODIFIER = {
    1: {
        "name": "Pratipada",
        "tone": "Initiation",
        "ahimsa_vow": (
            "Begin a new Anuvrata today — choose one small vow (abstaining from "
            "a specific food, a harmful habit, or a reactive speech pattern) and "
            "formally declare it before dawn. Maintain it for this entire paksha cycle."
        ),
        "samayika_window": "Early morning (5:30–7:00 AM)",
        "fast_intensity": 0,
    },
    2: {
        "name": "Dvitiya",
        "tone": "Receptivity",
        "ahimsa_vow": (
            "Offer water to any plants, trees, or garden near your home. The act "
            "of sustaining Sthavara (immobile) life consciously counters the "
            "inadvertent Sthavara-Himsa accumulated through daily movement and cooking."
        ),
        "samayika_window": "Early morning (5:30–7:00 AM)",
        "fast_intensity": 0,
    },
    3: {
        "name": "Tritiya",
        "tone": "Cultivation",
        "ahimsa_vow": (
            "Observe Mrishavada-Viramana (abstention from false speech) for the "
            "entire day. Commit to speaking only what you know to be true, and "
            "remaining silent when uncertain — silence is always more Ahimsa than "
            "a half-truth."
        ),
        "samayika_window": "Early morning (5:30–7:00 AM)",
        "fast_intensity": 0,
    },
    4: {
        "name": "Chaturthi",
        "tone": "Integration",
        "ahimsa_vow": (
            "Refrain from all use of leather, silk, and products involving direct "
            "violence in their production. If you discover any in current use, "
            "set a concrete intention to find an alternative within the next "
            "fourteen days — Aparigraha includes not holding what harms others."
        ),
        "samayika_window": "Dawn (5:00–6:30 AM)",
        "fast_intensity": 0,
    },
    5: {
        "name": "Panchami",
        "tone": "Expansion",
        "ahimsa_vow": (
            "Observe Ekasana — take only one meal today, before sunset. Choose "
            "food free of root vegetables, multi-sense organisms, and night-cooked "
            "items. The Panchami Ekasana is a traditional Jain observance marking "
            "the fifth-tithi sanctity of restraint."
        ),
        "samayika_window": "Dawn (5:00–6:30 AM)",
        "fast_intensity": 1,
    },
    6: {
        "name": "Shashthi",
        "tone": "Expression",
        "ahimsa_vow": (
            "Maintain Ratra-Bhojana-Viramana (abstaining from eating after "
            "sunset) from today's dusk onward through the rest of this paksha. "
            "Even a single sustained evening fast creates significant Asrava-"
            "nirodha (blockage of karmic influx through the Yoga of consumption)."
        ),
        "samayika_window": "Dawn (5:00–6:30 AM)",
        "fast_intensity": 0,
    },
    7: {
        "name": "Saptami",
        "tone": "Deepening",
        "ahimsa_vow": (
            "Perform one hour of mental Pratikraman without spoken words: "
            "mentally review the past six days for Kashayas expressed in thought, "
            "speech, and action, and silently request forgiveness from each being "
            "affected. Written reflection deepens the practice."
        ),
        "samayika_window": "Dawn (4:30–6:00 AM)",
        "fast_intensity": 0,
    },
    8: {
        "name": "Ashtami",
        "tone": "Purification",
        "ahimsa_vow": (
            "Observe Paushadha — eat one meal before noon, abstaining from root "
            "vegetables, honey, and all multi-sense organism foods. Spend the time "
            "freed by reduced eating in Svadhyaya or Samayika. The Ashtami "
            "Paushadha is among the most powerful Jain observances for shedding "
            "Mohaniya and Vedaniya Karma."
        ),
        "samayika_window": "Twilight (6:00–7:30 PM)",
        "fast_intensity": 3,
    },
    9: {
        "name": "Navami",
        "tone": "Intensification",
        "ahimsa_vow": (
            "Practice Mauna (sacred silence) for three full hours during the "
            "day's most socially active period — precisely when you would "
            "normally speak most. Use this silence as Vak-Yoga Samvara: the "
            "arrest of speech-based karmic influx at its primary channel."
        ),
        "samayika_window": "Dawn (4:30–6:00 AM)",
        "fast_intensity": 0,
    },
    10: {
        "name": "Dashami",
        "tone": "Stability",
        "ahimsa_vow": (
            "Offer Kshamapana (forgiveness request) to one being with whom you "
            "hold residual tension, resentment, or unresolved conflict — a brief, "
            "sincere inner or spoken gesture of release. The Dashami is the "
            "tithi of emotional stabilisation; this act directly sheds "
            "Krodha-Mohaniya Pudgalas."
        ),
        "samayika_window": "Dawn (4:30–6:00 AM)",
        "fast_intensity": 0,
    },
    11: {
        "name": "Ekadashi",
        "tone": "Transcendence",
        "ahimsa_vow": (
            "Observe Ayambil — eat only one meal of simple, completely unspiced, "
            "unseasoned, non-fried food before noon. Avoid fermented foods, root "
            "vegetables, and all multi-sense organism foods. The Ekadashi Ayambil "
            "is the specific fast of transcendence over sensory attachment."
        ),
        "samayika_window": "Dawn (4:30–6:00 AM)",
        "fast_intensity": 2,
    },
    12: {
        "name": "Dvadashi",
        "tone": "Consolidation",
        "ahimsa_vow": (
            "Give one meal or its equivalent in value to a being in genuine need "
            "today, without expectation of return, acknowledgment, or even "
            "knowledge of your identity. This is the Dana-Punya of the twelfth "
            "Tithi — anonymous giving prevents Mana-Kashaya from converting "
            "Dana into a status transaction."
        ),
        "samayika_window": "Dawn (4:30–6:00 AM)",
        "fast_intensity": 1,
    },
    13: {
        "name": "Trayodashi",
        "tone": "Surrender",
        "ahimsa_vow": (
            "Review your Parigraha (possessions and inner attachments) with "
            "Viveka today. Identify three objects or relationships held beyond "
            "genuine need and set a concrete intention to release one of them "
            "within this moon cycle. Trayodashi is the Tithi of approaching "
            "release; prepare the ground."
        ),
        "samayika_window": "Dawn (4:00–5:30 AM)",
        "fast_intensity": 1,
    },
    14: {
        "name": "Chaturdashi",
        "tone": "Liberation",
        "ahimsa_vow": (
            "Perform Pratikraman at dusk, formally confessing all transgressions "
            "against five-sensed beings committed since the last Chaturdashi, "
            "requesting forgiveness from the entire community of living beings "
            "across all six realms of Jain cosmology. Do not omit any being, "
            "however small."
        ),
        "samayika_window": "Twilight (6:00–7:30 PM)",
        "fast_intensity": 3,
    },
    15: {
        "name": "Purnima",
        "tone": "Fullness",
        "ahimsa_vow": (
            "Maintain Mauna (sacred silence) for 48 minutes during the Samayika "
            "window. Avoid all green vegetables today. If possible, observe a "
            "complete Upavasa — only boiled water taken after sunrise. The "
            "Purnima is the most powerful Tithi for Nirjara; every minute of "
            "genuine practice today carries exceptional weight."
        ),
        "samayika_window": "Pre-dawn (3:30–5:00 AM)",
        "fast_intensity": 3,
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — VERSE_LIBRARY
# 25 entries covering all verse_keys referenced in NAKSHATRA_DATA above.
# Sources: Tattvartha Sutra (TS), Uttaradhyayana Sutra (US),
#          Niyamasara (NS), Samayasara (SS), Dasavaikalika Sutra (DV)
# ═══════════════════════════════════════════════════════════════════════════════
VERSE_LIBRARY = {
    "TS_1_1": {
        "source": "Tattvartha Sutra 1.1 (Umasvati)",
        "transliteration": "samyag-darsana-jnana-caritrani moksa-margah",
        "meaning": (
            "Right perception, right knowledge, and right conduct together "
            "constitute the path to liberation. This foundational sutra of "
            "Umasvati establishes that Moksha is not grace from without but the "
            "natural result of the soul's own complete threefold self-realisation."
        ),
        "theme": "Moksha",
    },
    "TS_1_4": {
        "source": "[Attributed to Tattvartha Sutra Chapter 1, Umasvati tradition]",
        "transliteration": "pramana-nayair adhigamah",
        "meaning": (
            "Reality is comprehended through Pramanas (valid means of knowledge) "
            "and Nayas (partial standpoints). No single perspective captures the "
            "whole; the Anekanta-vada (doctrine of many-sidedness) ensures the "
            "Jiva approaches truth without the binding rigidity of Mithya-Drashti."
        ),
        "theme": "Samyak-Jnana",
    },
    "TS_6_1": {
        "source": "[Attributed to Tattvartha Sutra Chapter 6, Umasvati tradition]",
        "transliteration": "kaya-van-manah-karma yoga ityuchyate",
        "meaning": (
            "The activities of body, speech, and mind are designated Yoga — "
            "the three channels through which karma-matter (Pudgala) flows into "
            "the soul's field, constituting the mechanism of karmic influx "
            "(Asrava). Restraining these three Yogas is the beginning of Samvara."
        ),
        "theme": "Karma",
    },
    "TS_8_2": {
        "source": "[Attributed to Tattvartha Sutra Chapter 8, Umasvati tradition]",
        "transliteration": "mithya-drashty-avirata-pramatta-yogina-bandha-hetavah",
        "meaning": (
            "Wrong perception (Mithya-Drashti), lack of restraint (Avirata), "
            "heedlessness (Pramada), and the activities of body-speech-mind "
            "(Yoga) are the four causes through which Karma Pudgalas bind to "
            "the soul, extending the cycle of Samsara."
        ),
        "theme": "Karma",
    },
    "TS_8_14": {
        "source": "[Attributed to Tattvartha Sutra Chapter 8, Umasvati tradition]",
        "transliteration": "anubhava-sthiti-pradesa-karma-parinamanam",
        "meaning": (
            "Karma transforms according to its four dimensions: fruition-intensity "
            "(Anubhava), duration (Sthiti), quantum (Pradesha), and nature "
            "(Svabhava) — each dimension set at the moment of binding and "
            "alterable only through conscious Nirjara undertaken with Samyak-Bhava."
        ),
        "theme": "Karma",
    },
    "TS_9_1": {
        "source": "[Attributed to Tattvartha Sutra Chapter 9, Umasvati tradition]",
        "transliteration": "asrava-viparyayah samvarah",
        "meaning": (
            "Samvara — the arrest of karmic influx — is the direct reversal of "
            "Asrava and constitutes the first active movement of the soul toward "
            "liberation, achieved through the practice of the fifty-seven Samvara "
            "methods enumerated across the Agamic literature."
        ),
        "theme": "Nirjara",
    },
    "TS_9_3": {
        "source": "[Attributed to Tattvartha Sutra Chapter 9, Umasvati tradition]",
        "transliteration": "tapasa nirjara ca",
        "meaning": (
            "Through Tapa (austerity) previously accumulated karma is shed "
            "(Nirjara) from the soul's field. This is the second movement in "
            "the liberation process, following Samvara, and constitutes the "
            "active cleansing of Pudgalas already bound to the Jiva."
        ),
        "theme": "Nirjara",
    },
    "TS_9_7": {
        "source": "[Attributed to Tattvartha Sutra Chapter 9, Umasvati tradition]",
        "transliteration": (
            "anasanam avamaudarya-vritti-parisankhyana-rasa-parityaga-"
            "vivikta-sayyasana-kaya-klesa iti bahya-tapah"
        ),
        "meaning": (
            "The six external austerities (Bahya Tapa) — fasting (Anasana), "
            "reduced eating (Avamaudarya), limiting food intake (Vritti-parisankhyana), "
            "relinquishing tastes (Rasa-parityaga), solitary living "
            "(Vivikta-sayyasana), and mortification (Kaya-klesa) — constitute "
            "the six prescribed channels for active karmic shedding."
        ),
        "theme": "Nirjara",
    },
    "TS_10_1": {
        "source": "[Attributed to Tattvartha Sutra Chapter 10, Umasvati tradition]",
        "transliteration": "sa-hetu-karma-nirjaro moksha-margo bhavati",
        "meaning": (
            "Liberation arises when the soul achieves complete Nirjara — the "
            "total shedding of all previously bound Karma Pudgalas — combined "
            "with Samvara such that no new Asrava occurs, leaving the Jiva in "
            "its pure, unconditioned Siddha state of infinite knowledge and bliss."
        ),
        "theme": "Moksha",
    },
    "TS_10_7": {
        "source": "[Attributed to Tattvartha Sutra Chapter 10, Umasvati tradition]",
        "transliteration": (
            "ananta-jnana-darsana-sukha-virya-svarupah siddha-paramesthi"
        ),
        "meaning": (
            "The liberated soul (Siddha-Paramesthi) is characterised by infinite "
            "knowledge (Ananta-Jnana), infinite perception (Ananta-Darshana), "
            "infinite bliss (Ananta-Sukha), and infinite energy (Ananta-Virya) "
            "— the four attributes of the soul revealed when every last Pudgala "
            "of karma has been shed."
        ),
        "theme": "Moksha",
    },
    "US_28_14": {
        "source": "[Attributed to Uttaradhyayana Sutra, Chapter 28 tradition]",
        "transliteration": (
            "savve jiva vi icchanti, jivium na maritum; "
            "tasma na himsa kayavva, saccam etam sunissiya"
        ),
        "meaning": (
            "All living beings desire to live, not to die; therefore let no "
            "violence be done to any being — having heard this truth, hold it "
            "as the supreme law. This is the Agamic foundation of Ahimsa as "
            "mechanical cosmic principle, not as moral commandment from a deity."
        ),
        "theme": "Ahimsa",
    },
    "US_28_29": {
        "source": "[Attributed to Uttaradhyayana Sutra, Chapter 28 tradition]",
        "transliteration": (
            "ko vai-riyam na janai, ko va banham na passai; "
            "padilehittae appane, kasaya-malavihunam karejja"
        ),
        "meaning": (
            "Who does not know enmity? Who does not see bondage? Let one examine "
            "oneself and purify the soul of the impurities of passion "
            "(Kashaya-mala) — this is the primary work of the Dharma practitioner "
            "as articulated in the Uttaradhyayana teaching lineage."
        ),
        "theme": "Karma",
    },
    "US_28_34": {
        "source": "[Attributed to Uttaradhyayana Sutra, Chapter 28 tradition]",
        "transliteration": (
            "lobho vi bandhano vutto, moho vi bandhano vutto; "
            "pariggaho vi bandhano vutto, savvo pariggaho bahu"
        ),
        "meaning": (
            "Greed is declared bondage; delusion is declared bondage; "
            "possessiveness is declared bondage — all forms of Parigraha "
            "(attachment and acquisition) constitute the binding of the Jiva to "
            "the perpetual cycle of birth, suffering, and death."
        ),
        "theme": "Karma",
    },
    "US_29_3": {
        "source": "[Attributed to Uttaradhyayana Sutra 29, Leshya chapter tradition]",
        "transliteration": (
            "lessa chha pannatta: krishna, nila ya kapota ya; "
            "teyalessa ya pamma ya, shukka ya uttama lessa"
        ),
        "meaning": (
            "Six Leshyas are proclaimed: Krishna (black), Nila (blue), Kapota "
            "(grey), Teja/Pita (yellow), Padma (lotus/pink), and Shukla (white/ "
            "pure) — the six vibrational grades of the soul's karmic colouration, "
            "ascending from the densest to the most refined state approaching liberation."
        ),
        "theme": "Leshya",
    },
    "US_29_7": {
        "source": "[Attributed to Uttaradhyayana Sutra 29, Leshya chapter tradition]",
        "transliteration": (
            "krishna-lessiyo havanti, te dukkha-bhagino nara; "
            "jaha vauttam bijam va, taha karma-nimijjhiyam"
        ),
        "meaning": (
            "Those dwelling in Krishna Leshya are sharers of suffering — just "
            "as a seed thrown into soil takes deep root, so karma sown in the "
            "dense field of Krishna Leshya takes firm root in the Jiva's karmic "
            "body and requires sustained Nirjara effort to uproot."
        ),
        "theme": "Leshya",
    },
    "US_29_14": {
        "source": "[Attributed to Uttaradhyayana Sutra 29, Leshya chapter tradition]",
        "transliteration": (
            "jaha se puriso neyam pajjovaya-divasam; "
            "evam lessiyo puriso, jam-bhaviyam karihi"
        ),
        "meaning": (
            "As a person sees clearly by the light of a lamp, so one endowed "
            "with an elevated Leshya perceives the nature of karma and its "
            "consequences with clarity, acting consistently from Viveka "
            "(discrimination) rather than from Kashaya (passion)."
        ),
        "theme": "Leshya",
    },
    "US_29_21": {
        "source": "[Attributed to Uttaradhyayana Sutra 29, Leshya chapter tradition]",
        "transliteration": (
            "pamma-lessiyo ya nara, suhumam pi na hinsamti; "
            "padilehittae appane, savva-bhuyahitam icchanti"
        ),
        "meaning": (
            "Those of Padma (lotus) Leshya do not harm even the most subtle "
            "living beings; examining themselves constantly, they actively seek "
            "the welfare of all beings — this sustained orientation of goodwill "
            "is the mark and the practice of the Padma-Leshyi practitioner."
        ),
        "theme": "Leshya",
    },
    "NS_1_3": {
        "source": "[Attributed to Niyamasara, Kundakunda tradition]",
        "transliteration": (
            "jo janai savve bhave, niyamena so suhi hoi; "
            "avijjanarn bhava-rannam, na mucci sambhavenam"
        ),
        "meaning": (
            "One who knows all states of being through the discipline of Niyama "
            "(self-regulation) attains liberation; one who remains in the forest "
            "of ignorance (Avijja) is not released merely by birth in auspicious "
            "realms — knowledge without practice, and practice without right "
            "knowledge, both fall short."
        ),
        "theme": "Samyak-Darshana",
    },
    "NS_1_8": {
        "source": "[Attributed to Niyamasara, Kundakunda tradition]",
        "transliteration": (
            "shuddha-upayoga-lakshano so atma-tattva; "
            "raga-dosa-vimukkho ya, paramam sukham icchati"
        ),
        "meaning": (
            "The pure soul is characterised by Shuddha-Upayoga — pure "
            "consciousness-application completely free from Raga (attraction) "
            "and Dvesha (aversion) in all circumstances. This condition, not any "
            "external purity of body or ritual, is the Atma-tattva (soul-truth) "
            "that Kundakunda places at the centre of Jain practice."
        ),
        "theme": "Pudgala",
    },
    "NS_1_10": {
        "source": "[Attributed to Niyamasara, Kundakunda tradition]",
        "transliteration": (
            "jiva-ajiva-viveko ya, savva-dukkhassa muccanam; "
            "bandhassa ya vimokkhassa, idha sammattam ucchiyam"
        ),
        "meaning": (
            "The discrimination between Jiva (soul) and Ajiva (non-soul) is the "
            "direct cause of release from all suffering; Samyak-Darshana (right "
            "perception) is declared the foremost wisdom on the path to "
            "liberation — without this clear seeing, all practice remains Mithya."
        ),
        "theme": "Samyak-Darshana",
    },
    "SS_1_1": {
        "source": "[Attributed to Samayasara, Kundakunda tradition]",
        "transliteration": (
            "jo jaedi appana jam-sahavam, so jaedi savva-bhave; "
            "jo na jaedi appana, kaho so savva-bhave jane"
        ),
        "meaning": (
            "One who knows the intrinsic nature of the self knows all states of "
            "existence; one who does not know the self — how can such a one know "
            "anything at all? The Samayasara places self-knowledge as both the "
            "foundation and the summit of the entire Jain spiritual path."
        ),
        "theme": "Moksha",
    },
    "SS_1_4": {
        "source": "[Attributed to Samayasara, Kundakunda tradition]",
        "transliteration": (
            "jam shuddha-upaya-lakkhano, so atma paramattham; "
            "savvannuhi pannitam, tado param na atthi"
        ),
        "meaning": (
            "That which is characterised by pure consciousness-application "
            "(Shuddha-Upayoga) is the soul in its ultimate reality (Paramartha) "
            "— so proclaimed by the omniscient ones. Beyond this pure witnessing "
            "awareness there is nothing higher to be attained or known."
        ),
        "theme": "Moksha",
    },
    "SS_1_7": {
        "source": "[Attributed to Samayasara, Kundakunda tradition]",
        "transliteration": (
            "jaha davvam na hoi akariyam, taha paryayam na hoi akariyam; "
            "taha cheva atma na hoi, savvam param nishchayado"
        ),
        "meaning": (
            "As a substance cannot exist without its modes, and modes cannot "
            "exist without a substance, so the soul's liberation is not separate "
            "from its fundamental being — all is understood from the standpoint "
            "of ultimate reality (Nishchaya-Naya) beyond conventional designation."
        ),
        "theme": "Moksha",
    },
    "DV_1_1": {
        "source": "[Attributed to Dasavaikalika Sutra Chapter 1, tradition of Shayyambhava]",
        "transliteration": (
            "dharmo mangalam ukkittham, ahimsa sanjamo tavo; "
            "deva vi tam namamsanti, jassa dhamme saya mano"
        ),
        "meaning": (
            "Dharma is proclaimed the highest auspiciousness: Ahimsa "
            "(non-violence), Sanyama (restraint), and Tapa (austerity). Even "
            "celestial beings bow to one whose mind is constantly established "
            "in Dharma — so teaches the opening verse of the Dasavaikalika Sutra."
        ),
        "theme": "Ahimsa",
    },
    "DV_4_8": {
        "source": "[Attributed to Dasavaikalika Sutra Chapter 4, monastic conduct tradition]",
        "transliteration": (
            "savvao panchindriya-savvahinsa-viradassa ya; "
            "siya jaya-visaya-thio, eso sanniya-savvao"
        ),
        "meaning": (
            "Completely abstaining from injury to all five-sensed beings and "
            "fully restraining the five senses — remaining established in the "
            "field of victory over sense-objects — this complete Sanyama is "
            "declared the fullness of the monk's vow as prescribed in the "
            "Dasavaikalika's chapter on conduct."
        ),
        "theme": "Ahimsa",
    },
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

    # Tithi: every 12° difference = 1 tithi
    diff        = (moon_lon - sun_lon) % 360
    tithi_index = int(diff / 12) + 1            # 1–30
    tithi_name  = TITHI_NAMES[min(tithi_index - 1, 14)]
    paksha      = "Shukla (Bright)" if tithi_index <= 15 else "Krishna (Dark)"

    # Nakshatra: moon traverses 27 nakshatras in 360°
    nakshatra_index = int(moon_lon / (360 / 27))
    nakshatra_name  = NAKSHATRA_NAMES[nakshatra_index % 27]

    # Moon phase percentage
    moon.compute(observer)
    phase_pct = round(moon.phase, 2)

    dharma = TITHI_DHARMA.get(tithi_index, {
        "fast": "Regular mindful eating (Mitahara)",
        "diet": "Follow standard Jain diet: no root vegetables, no eating after sunset.",
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


# ── AI system prompt and user prompt builder (USE_AI = True path) ─────────────
# These remain intact and are used only when USE_AI is set back to True.

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
5. Reference Leshya (karmic colouration: Krishna, Nila, Kapota, Pita, Padma, Shukla) when relevant.
6. Ground every prediction in the 8 Karma types: Jnanavaraniya, Darshanavarniya, Vedaniya,
   Mohaniya, Ayushya, Nama, Gotra, Antaraya.

OUTPUT STRUCTURE (respond in valid JSON only):
{
  "daily_reading": "3-4 sentences synthesizing the Tithi and Nakshatra energy through a Jain lens.",
  "karma_focus": "One specific karmic type active today and the Nirjara path to shed it.",
  "leshya_guidance": "Which of the 6 Leshyas is dominant today and a tip to elevate toward Shukla.",
  "ahimsa_action": "One concrete micro-action of Ahimsa, Satya, or Aparigraha for today's Tithi.",
  "samayika_muhurta": "Best time window today for 48-minute Samayika meditation and why.",
  "verse_reflection": "One authentic shloka from Jain Agamas relevant to today (transliterated + meaning).",
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


# ── Deterministic 3-layer combinatorial reading engine ────────────────────────
def generate_deterministic_reading(astro: dict, language: str) -> dict:
    """
    Produces a fully deterministic Jain daily reading by combining NAKSHATRA_DATA,
    TITHI_MODIFIER, and VERSE_LIBRARY. No external API calls. Always returns a
    valid 7-key dict; falls back to Namokar Mantra on any exception.
    """
    LESHYA_ELEVATION = {
        "Krishna": (
            "Your karmic field resonates with Krishna Leshya — the densest "
            "vibrational state described in the Uttaradhyayana's Leshya chapter. "
            "Practice 5 minutes of Kayotsarga (body-abandonment meditation) "
            "immediately upon waking to begin loosening these Karma Pudgalas "
            "before the day's activities bind new ones."
        ),
        "Nila": (
            "Nila Leshya indicates restlessness and reactive turbulence of the "
            "Jiva. Recite the Namokar Mantra 108 times with a tulsi mala to "
            "stabilise the Pranic field before noon — the mantra's Pudgala "
            "vibrations directly counter Nila's agitated frequency."
        ),
        "Kapota": (
            "Kapota (grey) Leshya reflects confused discrimination — the Jiva "
            "cannot clearly distinguish Dharma from Adharma, self from non-self. "
            "Study one Sutra from the Tattvartha Sutra today: even a single verse "
            "read with genuine intention initiates the clarifying process of "
            "Samyak-Jnana."
        ),
        "Pita": (
            "Pita (yellow) Leshya marks the threshold of genuine spiritual "
            "momentum — the Jiva is rising toward clarity. Your discrimination "
            "is strengthening. Channel this rising energy through Svadhyaya "
            "(scriptural self-study) for 20 minutes today to consolidate the "
            "upward movement."
        ),
        "Padma": (
            "Padma (lotus) Leshya — the Jiva is in a refined and receptive "
            "state. Maintain this elevation by practising total Ahimsa in "
            "speech today: let no harsh, careless, or untrue word leave your "
            "lips. The Padma state is preserved by the precise quality of "
            "Vak-Yoga (speech conduct)."
        ),
        "Shukla": (
            "Shukla Leshya — the purest karmic colouration, closely "
            "approximating the Siddha state described in the Samayasara. "
            "Dedicate today's Samayika entirely to Shuddha-Upayoga: pure, "
            "object-free awareness with no mantra, no visualisation, no "
            "framework — only the Jiva resting in its own luminous nature."
        ),
    }

    try:
        # A. Extract inputs
        nakshatra_name = astro["nakshatra"]
        tithi_number   = int(astro["tithi_number"])
        paksha         = astro["paksha"]
        moon_phase_pct = astro.get("moon_phase_pct", 0.0)

        # Normalise tithi to 1–15 range for TITHI_MODIFIER lookup.
        # Krishna paksha tithis (16–30) are mirrored onto Shukla 15–1.
        tithi_key = tithi_number if tithi_number <= 15 else 30 - tithi_number + 1

        # B. Fetch from layers (fall back to first entry on unknown key)
        nak   = NAKSHATRA_DATA.get(nakshatra_name, NAKSHATRA_DATA["Ashvini"])
        tith  = TITHI_MODIFIER.get(tithi_key, TITHI_MODIFIER[1])
        verse = VERSE_LIBRARY.get(nak["verse_key"], list(VERSE_LIBRARY.values())[0])

        # C. Paksha tone
        if "Shukla" in paksha:
            paksha_tone = (
                "The waxing lunar energy amplifies outward karma-shedding "
                "through action, Seva (selfless service), and active engagement "
                "with the Sangha and the world of beings."
            )
        else:
            paksha_tone = (
                "The waning lunar energy draws the Jiva inward toward "
                "Pratyahara — withdrawal, silence, and subtle Nirjara through "
                "meditation and consciously reduced sensory engagement."
            )

        # D. Assemble daily_reading (3–4 rich sentences)
        daily_reading = (
            nak["base_energy"]
            + " "
            + f"Under the {tith['tone']} influence of {tith['name']} Tithi, "
            + paksha_tone
        )

        # E. Assemble karma_focus
        karma_focus = (
            f"Today's active karma is {nak['karma_type']}. "
            f"The prescribed Nirjara (karmic shedding) path for "
            f"{nakshatra_name} Nakshatra is: {nak['nirjara_path']}. "
            f"{tith['ahimsa_vow']}"
        )

        # F. Assemble leshya_guidance
        dominant       = nak["leshya"]
        leshya_guidance = (
            f"Dominant Leshya today: {dominant}. "
            + LESHYA_ELEVATION[dominant]
        )

        # G. Compute shreni_meter (1–10, shifts every day)
        day_of_year  = datetime.now(timezone.utc).timetuple().tm_yday
        base         = (tithi_number + day_of_year) % 10 + 1
        auspicious   = [5, 8, 11, 14, 15]
        boost        = 1 if tithi_key in auspicious else 0
        paksha_boost = 1 if "Shukla" in paksha else 0
        shreni       = min(base + boost + paksha_boost, 10)

        # H. Format verse_reflection
        verse_reflection = (
            f"{verse['transliteration']}\n"
            f"— {verse['source']}\n\n"
            f"Meaning: {verse['meaning']}"
        )

        # I. Assemble samayika_muhurta
        fast_labels = ["Normal Jain diet", "Ekasana", "Ayambil", "Upavasa"]
        samayika_muhurta = (
            f"{tith['samayika_window']} — 48-minute Samayika recommended. "
            f"Fast intensity today: {fast_labels[tith['fast_intensity']]}."
        )

        # J. Language note
        if language in ("Hindi", "Gujarati"):
            daily_reading += (
                f" [Translation to {language} coming in next update. "
                f"Reading provided in English for accuracy.]"
            )

        return {
            "daily_reading":    daily_reading,
            "karma_focus":      karma_focus,
            "leshya_guidance":  leshya_guidance,
            "ahimsa_action":    tith["ahimsa_vow"],
            "samayika_muhurta": samayika_muhurta,
            "verse_reflection": verse_reflection,
            "shreni_meter":     shreni,
        }

    except Exception as exc:
        # Safe fallback — always returns a valid 7-key dict
        fallback_verse = (
            "Namo Arihantanam. Namo Siddhanam. Namo Ayariyanam.\n"
            "Namo Uvajjhayanam. Namo Loe Savva-Sahunam.\n\n"
            "The Namokar Mantra — the supreme salutation to the five "
            "transcendent beings — is always a valid Nirjara practice."
        )
        return {
            "daily_reading": (
                "The reading engine encountered an unexpected configuration. "
                "Recite the Namokar Mantra 108 times and begin the day in "
                "Samabhava (equanimity). Every moment of conscious awareness "
                "is Nirjara. "
                f"[Internal note: {str(exc)[:120]}]"
            ),
            "karma_focus": (
                "Focus on Mohaniya Karma today — the source of all confusion. "
                "The Nirjara path is Samayika: 48 minutes of still, equanimous "
                "non-reactive presence."
            ),
            "leshya_guidance": (
                "Dominant Leshya: Kapota (grey). Recite the Namokar Mantra "
                "to stabilise the Darshana faculty toward clarity."
            ),
            "ahimsa_action": (
                "Observe complete Ahimsa in speech for the next two hours — "
                "speak only what is true, necessary, and kind."
            ),
            "samayika_muhurta": (
                "Dawn (5:00–6:30 AM) — 48-minute Samayika recommended. "
                "Fast intensity today: Normal Jain diet."
            ),
            "verse_reflection": fallback_verse,
            "shreni_meter": 5,
        }


# ── Request / Response models ─────────────────────────────────────────────────
class HoroscopeRequest(BaseModel):
    user_id:   str
    latitude:  float
    longitude: float
    language:  str = "English"    # English | Hindi | Gujarati


class HoroscopeResponse(BaseModel):
    astro_data:   dict
    reading:      dict
    generated_at: str


# ── Main endpoint ─────────────────────────────────────────────────────────────
@app.post("/generate-horoscope", response_model=HoroscopeResponse)
async def generate_horoscope(req: HoroscopeRequest):
    now = datetime.now(timezone.utc)

    # 1. Astronomical calculation
    try:
        astro = calculate_jain_positions(req.latitude, req.longitude, now)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Astro calculation error: {e}")

    # 2. Reading generation
    if USE_AI:
        # ── Anthropic/Claude path (restore when USE_AI = True) ────────────────
        try:
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                system=JAIN_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_user_prompt(astro, req.language)}],
            )
            reading = json.loads(response.content[0].text)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AI generation error: {e}")
    else:
        # ── Deterministic engine ──────────────────────────────────────────────
        try:
            reading = generate_deterministic_reading(astro, req.language)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Reading engine error: {str(e)}",
            )

    # 3. Save to Supabase (non-fatal)
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
        print(f"Supabase save warning: {e}")    # non-fatal

    return HoroscopeResponse(
        astro_data=astro,
        reading=reading,
        generated_at=now.isoformat(),
    )


# ── Diagnostic endpoint ───────────────────────────────────────────────────────
@app.get("/reading-preview")
def reading_preview():
    """Returns a sample deterministic reading using hardcoded test values.
    Use this to verify the engine works without calling /generate-horoscope."""
    test_astro = {
        "tithi_number":    8,
        "tithi_name":      "Ashtami",
        "paksha":          "Shukla (Bright)",
        "nakshatra":       "Pushya",
        "nakshatra_index": 8,
        "moon_longitude":  93.5,
        "moon_phase_pct":  52.3,
        "fast_guidance":   "Ashtami fast",
        "diet_guidance":   "No root vegetables",
        "calculated_at":   datetime.now(timezone.utc).isoformat(),
    }
    return {
        "engine":       "deterministic",
        "use_ai":       USE_AI,
        "test_reading": generate_deterministic_reading(test_astro, "English"),
    }


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "om", "service": "Jain Jyotish API"}
