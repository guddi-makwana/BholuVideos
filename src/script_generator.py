import json
import logging
import secrets
import uuid
from typing import Any, Dict, List, Tuple
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from src.config import (
    BHOLU_CHARACTER_PROMPT,
    CARTOON_STYLE_PREFIX,
    GEMINI_MODEL,
    USED_TOPICS_FILE,
    get_gemini_api_keys,
)

logger = logging.getLogger(__name__)

# 30 distinct global ancient civilizations/eras to prevent LLM mode collapse
ANCIENT_CIVILIZATIONS: List[Tuple[str, str]] = [
    ("Sumer & Akkad (Mesopotamia, 3000–2000 BCE)", "ziggurats, cuneiform tablets, Tigris-Euphrates canals, bronze helmets"),
    ("Old & New Kingdom Egypt (2600–1070 BCE)", "limestone temples, Nile barges, золотые pharaonic regalia, desert obelisks"),
    ("Indus Valley Civilization — Harappa & Mohenjo-daro (2500–1900 BCE)", "baked-brick citadels, Great Bath, carved soapstone seals, merchant caravans"),
    ("Shang & Zhou Dynasty China (1600–256 BCE)", "bronze ritual vessels, oracle bones, jade axes, war chariots"),
    ("Minoan & Mycenaean Bronze Age Aegean (2000–1100 BCE)", "Knossos frescoed palaces, bull-leaping courtyards, cyclopean stone gates"),
    ("Hittite & Lydian Anatolia (1600–546 BCE)", "Hattusa Lion Gate, iron-forged weapons, Pactolus gold refineries"),
    ("Assyrian & Neo-Babylonian Empires (900–539 BCE)", "Ishtar Gate glazed blue bricks, winged lamassu statues, siege towers"),
    ("Phoenicia & Maritime Canaan (1200–539 BCE)", "Tyrian purple dye vats, cedar bireme ships, Mediterranean island ports"),
    ("Olmec & Zapotec Mesoamerica (1200 BCE–200 CE)", "colossal basalt heads, jungle step pyramids, jade jaguar masks, ballcourts"),
    ("Achaemenid Persian Empire (550–330 BCE)", "Persepolis apadana columns, Immortal guards, Royal Road courier relays"),
    ("Classical Greece — Athens, Sparta, Corinth, Thebes (500–323 BCE)", "marble acropolis, bronze hoplite phalanxes, trireme harbors, amphitheaters"),
    ("Early & Middle Roman Republic (509–133 BCE)", "Roman Forum rostra, manipular legions, senate curia, aqueduct arches"),
    ("Carthaginian Empire & Punic Mediterranean (650–146 BCE)", "Cothon circular naval harbor, North African war elephants, sacred temples"),
    ("Warring States & Qin Dynasty China (475–206 BCE)", "crossbow formations, terracotta-style armor, Great Wall mountain watchtowers"),
    ("Maurya & Shunga Empire India (322–73 BCE)", "Pataliputra wooden palaces, Ashoka pillars, imperial war elephants"),
    ("Hellenistic Kingdoms — Seleucid, Ptolemaic, Macedon, Pergamon (323–31 BCE)", "Pharos lighthouse, Great Library scrolls, silver-shield pikemen"),
    ("Han Dynasty & Three Kingdoms China (202 BCE–280 CE)", "Chang'an silk markets, repeating crossbows, seismoscopes, river fleet battles"),
    ("Scythian, Sarmatian & Xiongnu Steppe Confederations (800 BCE–200 CE)", "golden animal-style plaques, felt yurts, composite horse archers"),
    ("Chavín, Paracas, Nazca & Moche Andean Civilizations (900 BCE–600 CE)", "adobe huaca pyramids, desert geoglyphs, golden earspools, coastal reed boats"),
    ("Classic Maya City-States — Tikal, Calakmul, Palenque, Copán (250–900 CE)", "limestone jungle temples, feathered serpent crests, obsidian macuahuitl"),
    ("Parthian & Sassanid Persian Empires (247 BCE–651 CE)", "cataphract heavy cavalry, Ctesiphon great arch, fire temples"),
    ("Ancient Celtic Gaul, Britannia & Iceni (400 BCE–100 CE)", "hillforts, horned carnyx war trumpets, woad-painted chariot warriors, oak groves"),
    ("Nabataean Kingdom & Palmyra (300 BCE–273 CE)", "rose-red rock-carved Petra facades, incense spice caravans, desert cisterns"),
    ("Chola, Pandya & Chera Sangam Era South India (300 BCE–300 CE)", "granite gopuram towers, spice harbor ships, heroic poetry courts"),
    ("Yayoi & Kofun Period Japan (300 BCE–538 CE)", "keyhole-shaped kofun mounds, bronze dotaku bells, raised-floor granaries"),
    ("Gojoseon & Three Kingdoms Korea — Goguryeo, Baekje, Silla (300 BCE–668 CE)", "gold crowns, mountain stone fortresses, armored horse warriors"),
    ("Teotihuacan & Monte Albán Highland Mexico (100 BCE–550 CE)", "Avenue of the Dead, Pyramid of the Sun, feathered murals"),
    ("Gupta Empire & Golden Age India (320–550 CE)", "iron pillar, astronomical observatories, Nalanda courtyards"),
    ("Kingdom of Aksum & Ancient Horn of Africa (100–600 CE)", "giant carved granite stelae, Red Sea merchant dhows, gold coinage"),
    ("Bactria & Kushan Empire Central Asia (250 BCE–375 CE)", "Silk Road oasis citadels, Greco-Buddhist statues, mountain passes"),
]

STORY_ARCHETYPES: List[str] = [
    "an audacious military deception, battlefield trick, or tactical backfire",
    "a bizarre ancient law, courtroom trial, or strange royal decree",
    "an impossible ancient engineering feat, megaproject, or clever invention",
    "a high-stakes heist, espionage mission, or secret smuggling plot",
    "a legendary diplomatic insult that sparked an unexpected chain reaction",
    "an eccentric ruler's strange obsession, banquet, or experiment",
    "a desperate siege survival tactic or ingenious city defense",
    "an ancient economic scheme, counterfeit scandal, or trade monopoly",
    "a backfiring prophecy, oracle interpretation, or superstitious ritual",
    "an ancient sports, chariot race, or gladiator/ballgame scandal",
    "a bold impostor, palace conspiracy, or double-agent betrayal",
    "a catastrophic naval expedition or uncharted voyage",
]

SCENE_CAMERA_DIRECTIVES: List[str] = [
    "Extreme wide cinematic establishing angle from a high vantage point, expansive architectural depth, warm golden-hour rim lighting",
    "Dynamic low-angle medium action shot looking up at the central figure, dramatic diagonal shadows, vibrant high-contrast cel shading",
    "Intense close-up expressive character reaction shot with detailed facial emotion, shallow foreground framing, flickering torchlight glow",
    "Over-the-shoulder perspective looking into a bustling scene full of motion, layered foreground and background silhouettes, rich jewel-tone palette",
    "Dramatic Dutch-angle climax shot at the peak moment of action, dynamic motion lines, vivid sunset crimson and amber lighting",
    "Bird's-eye overhead tactical view showing the scale of the aftermath, sweeping environmental detail, cool twilight sapphire and gold contrast",
    "Panoramic eye-level tableau with strong foreground framing elements, expressive cartoon posture, crisp dramatic spotlighting",
]


class SceneSchema(BaseModel):
    narration: str = Field(
        description="1 to 2 punchy sentences of voiceover narration for this scene."
    )
    visual_prompt: str = Field(
        description=(
            "Detailed visual description of the scene starting with the mandatory "
            "2D western animated cartoon style prefix, featuring unique camera framing, "
            "distinct environment details, and specific character actions."
        )
    )


class ScriptSchema(BaseModel):
    topic: str = Field(
        description="Specific historical event name and year (e.g., 'The Lydian Coinage Reform of King Croesus (550 BCE)')."
    )
    youtube_title: str = Field(
        description="Catchy YouTube Shorts title (< 90 chars) ending with #shorts #ancienthistory."
    )
    youtube_description: str = Field(
        description="Engaging 2-sentence summary followed by 5 to 8 relevant hashtags (#shorts, #history, #ancienthistory, etc.)."
    )
    scenes: List[SceneSchema] = Field(
        description="Array of 5 to 7 scenes targeting a 35 to 50 second short-form video.",
        min_length=5,
        max_length=7,
    )


def load_used_topics() -> List[str]:
    """Load previously used historical topics from used_topics.json."""
    if not USED_TOPICS_FILE.exists():
        return []
    try:
        data = json.loads(USED_TOPICS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(item) for item in data]
    except Exception as exc:
        logger.warning("Could not parse %s: %s. Starting with empty list.", USED_TOPICS_FILE, exc)
    return []


def record_used_topic(topic: str) -> None:
    """Append a completed topic to used_topics.json if not already recorded."""
    topics = load_used_topics()
    if topic and topic not in topics:
        topics.append(topic)
        USED_TOPICS_FILE.write_text(
            json.dumps(topics, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logger.info("Recorded topic in %s: %s", USED_TOPICS_FILE.name, topic)


def _select_diverse_civilization_and_archetype(used_topics: List[str]) -> Tuple[str, str, str]:
    """
    Use cryptographic randomness to pick a civilization and story archetype that
    has not been recently used.
    """
    rng = secrets.SystemRandom()
    recent_lower = " ".join(used_topics[-15:]).lower()

    fresh_civs = [
        civ for civ in ANCIENT_CIVILIZATIONS
        if not any(word.lower() in recent_lower for word in civ[0].split() if len(word) > 4)
    ]
    pool = fresh_civs if fresh_civs else ANCIENT_CIVILIZATIONS
    civ_name, civ_visual_motifs = rng.choice(pool)
    archetype = rng.choice(STORY_ARCHETYPES)
    return civ_name, civ_visual_motifs, archetype


def _normalize_script_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure visual prompt prefixes, per-scene distinct camera/lighting directives,
    and YouTube title suffix constraints are strictly met so no two scenes ever look alike.
    """
    suffix = "#shorts #ancienthistory"
    title = str(payload.get("youtube_title", "")).strip()
    if not title.lower().endswith(suffix):
        for tag in ["#shorts", "#ancienthistory", "#history"]:
            if title.lower().endswith(tag):
                title = title[: -len(tag)].strip()
        max_base_len = 89 - len(suffix) - 1
        if len(title) > max_base_len:
            title = title[:max_base_len].rstrip(" -:,.")
        title = f"{title} {suffix}".strip()
    if len(title) >= 90:
        base_budget = 89 - len(suffix) - 1
        base_part = title[: -len(suffix)].strip()[:base_budget].rstrip(" -:,.")
        title = f"{base_part} {suffix}"
    payload["youtube_title"] = title

    rng = secrets.SystemRandom()
    shuffled_directives = rng.sample(
        SCENE_CAMERA_DIRECTIVES, k=len(SCENE_CAMERA_DIRECTIVES)
    )

    scenes = payload.get("scenes", [])
    normalized_scenes = []
    for idx, scene in enumerate(scenes):
        narration = str(scene.get("narration", "")).strip()
        visual_prompt = str(scene.get("visual_prompt", "")).strip()
        if visual_prompt.startswith(CARTOON_STYLE_PREFIX):
            core_desc = visual_prompt[len(CARTOON_STYLE_PREFIX) :].lstrip(": ")
        else:
            core_desc = visual_prompt.lstrip(": ")

        if "bholu" not in core_desc.lower() or "pink teddy bear" not in core_desc.lower():
            core_desc = f"{BHOLU_CHARACTER_PROMPT}in the scene: {core_desc}"

        camera_directive = shuffled_directives[idx % len(shuffled_directives)]
        if camera_directive.lower() not in core_desc.lower():
            core_desc = f"{core_desc.rstrip('. ')}. {camera_directive}."

        full_visual_prompt = f"{CARTOON_STYLE_PREFIX}{core_desc}"
        normalized_scenes.append(
            {
                "narration": narration,
                "visual_prompt": full_visual_prompt,
            }
        )
    payload["scenes"] = normalized_scenes
    return payload


def get_mock_script() -> Dict[str, Any]:
    """
    Built-in pool of distinct multi-scene Ancient History scripts for --mock-llm verification,
    randomly selecting a fresh script not in used_topics.json on each run.
    """
    mock_pool = [
        {
            "topic": "The Sacred Chickens of the Battle of Drepana (249 BCE)",
            "youtube_title": "When Rome Ignored the Sacred Chickens! #shorts #ancienthistory",
            "youtube_description": (
                "In 249 BCE, Roman Consul Publius Claudius Pulcher threw Rome's sacred oracle chickens "
                "overboard before the Battle of Drepana—leading to one of Rome's worst naval disasters. "
                "Would you have trusted the chickens? #shorts #history #ancienthistory #romanhistory #punicwars #cartoonhistory"
            ),
            "scenes": [
                {
                    "narration": "In Ancient Rome, no general dared go to war without first consulting a flock of sacred chickens!",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}A proud Roman consul in gleaming bronze armor and a crimson cape "
                        "standing on the wooden deck of a Roman warship at dawn, staring at an ornate wooden cage "
                        "holding plump white chickens while nervous sailors watch."
                    ),
                },
                {
                    "narration": "Before the naval Battle of Drepana in 249 BCE, Consul Publius Claudius Pulcher scattered sacred grain before the birds.",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}A solemn Roman augur priest kneeling on the ship deck scattering golden grain "
                        "on weathered oak planks while three seasick white chickens shiver in the salty breeze."
                    ),
                },
                {
                    "narration": "If the chickens ate eagerly, the gods promised victory—but that morning, the seasick birds refused to touch a single crumb!",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}Close-up of grumpy green-faced seasick white chickens turning their beaks away "
                        "from golden grain on the ship deck while terrified Roman legionaries gasp with wide eyes."
                    ),
                },
                {
                    "narration": "Furious at the bad omen, Pulcher shouted, 'If they will not eat, then let them drink!' and hurled the sacred chickens into the sea.",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}An enraged Roman commander tossing a wooden crate over the railing of a Roman trireme "
                        "into splashing turquoise Mediterranean waves while shocked soldiers grab their helmets."
                    ),
                },
                {
                    "narration": "Hours later, the Carthaginian fleet crushed his panicked crew and sank ninety-three Roman warships—proving you never mess with the sacred chickens!",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}A dramatic naval battle with Carthaginian warships ramming Roman triremes "
                        "under stormy skies while a smug white chicken floats safely in the foreground on a wooden shield."
                    ),
                },
            ],
        },
        {
            "topic": "Zhang Heng's Golden Dragon Earthquake Detector (132 CE)",
            "youtube_title": "China's Ancient Dragon Earthquake Machine! #shorts #ancienthistory",
            "youtube_description": (
                "In 132 CE, Han Dynasty polymath Zhang Heng invented a giant bronze vessel with eight dragons "
                "that detected earthquakes hundreds of miles away before anyone felt a tremor! "
                "#shorts #history #ancienthistory #handynasty #ancientchina #inventions"
            ),
            "scenes": [
                {
                    "narration": "In 132 CE, Han Dynasty scholar Zhang Heng unveiled a mysterious six-foot bronze urn inside the imperial court of Luoyang.",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}A bearded Chinese polymath in flowing silk robes presenting a giant ornate bronze urn "
                        "decorated with eight golden dragons surrounded by eight open-mouthed bronze toads in a grand Han palace."
                    ),
                },
                {
                    "narration": "Eight bronze dragons clung to the outside, each holding a heavy bronze ball in its jaws above a waiting bronze toad.",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}Extreme close-up of an intricately cast bronze dragon head clasping a gleaming copper sphere "
                        "in its teeth directly above a Squatting bronze toad with its mouth wide open."
                    ),
                },
                {
                    "narration": "Skeptical palace officials mocked the invention—until one afternoon, a single dragon's mouth snapped open with a deafening clang!",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}Startled Han court officials jumping back in shock as a bronze ball drops from the western dragon's mouth "
                        "into the toad below with dramatic sound-wave rings."
                    ),
                },
                {
                    "narration": "Nobody in the capital felt the ground shake, and Zhang Heng's rivals accused his machine of malfunctioning.",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}Arrogant court nobles in tall black hats pointing accusingly at the calm, smiling inventor "
                        "beside his bronze seismoscope inside a candlelit hall."
                    ),
                },
                {
                    "narration": "Four days later, a breathless messenger galloped in from Longxi, four hundred miles west, reporting a massive earthquake in the exact direction the dragon faced!",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}An exhausted imperial courier on a foaming horse bursting through the palace gates holding a scroll "
                        "while stunned ministers bow in awe before Zhang Heng."
                    ),
                },
            ],
        },
        {
            "topic": "The Great Babylonian Beer Law of Hammurabi (1750 BCE)",
            "youtube_title": "Babylon'sDeadly Law for Watered-Down Beer! #shorts #ancienthistory",
            "youtube_description": (
                "King Hammurabi of Babylon took beer so seriously that his famous stone law code included strict price caps "
                "and harsh penalties for tavern keepers who shortchanged customers! #shorts #history #ancienthistory #mesopotamia #babylon"
            ),
            "scenes": [
                {
                    "narration": "In Ancient Babylon, beer wasn't just a drink—it was daily wages, religious offerings, and serious legal business!",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}A lively Mesopotamian mud-brick tavern beside a canal where bearded Babylonian workers "
                        "sip golden barley beer through long reed straws from shared clay jars."
                    ),
                },
                {
                    "narration": "Around 1750 BCE, King Hammurabi carved two hundred eighty-two laws into a towering black basalt pillar in the center of Babylon.",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}King Hammurabi in a tall royal cylinder crown inspecting a towering polished black stone stele "
                        "covered in glowing cuneiform inscriptions under the blazing Mesopotamian sun."
                    ),
                },
                {
                    "narration": "Four of those royal laws targeted tavern keepers—almost all of whom were respected Babylonian priestesses and businesswomen!",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}A sharp-eyed Babylonian woman tavern keeper in colorful woven robes weighing silver and barley grain "
                        "on bronze scales behind a counter lined with amphorae."
                    ),
                },
                {
                    "narration": "Law One Hundred Eight decreed that if a tavern keeper watered down beer or overcharged for grain, she would be arrested on the spot.",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}Stern Babylonian royal inspectors holding bronze spears confronting a nervous merchant "
                        "pouring water into a clay fermentation vat."
                    ),
                },
                {
                    "narration": "The punishment was terrifyingly ironic: any brewer convicted of watering down beer was thrown directly into the Euphrates River!",
                    "visual_prompt": (
                        f"{CARTOON_STYLE_PREFIX}A dramatic wide view of the sparkling Euphrates River flowing past Babylon's blue glazed Ishtar walls "
                        "as shocked citizens watch from the stone quay."
                    ),
                },
            ],
        },
    ]
    used = set(load_used_topics())
    available = [s for s in mock_pool if s["topic"] not in used]
    chosen = secrets.SystemRandom().choice(available if available else mock_pool)
    return _normalize_script_payload(dict(chosen))


def generate_history_script(mock_llm: bool = False) -> Dict[str, Any]:
    """
    Generate a unique ancient history cartoon script using Google's google-genai SDK.
    Dynamically selects a randomized civilization, era, and story archetype per run
    and enforces distinct per-scene camera compositions.
    """
    if mock_llm:
        logger.info("Using built-in mock Ancient History script pool (--mock-llm enabled).")
        return get_mock_script()

    api_keys = get_gemini_api_keys()
    if not api_keys:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Provide a valid key or run with --mock-llm."
        )

    used_topics = load_used_topics()
    recent_topics = used_topics[-150:] if used_topics else []
    recent_topics_str = (
        "\n".join(f"- {t}" for t in recent_topics)
        if recent_topics
        else "None yet."
    )

    civ_name, civ_motifs, story_archetype = _select_diverse_civilization_and_archetype(used_topics)
    run_nonce = uuid.uuid4().hex[:12]

    logger.info(
        "Target Civilization: %s | Story Archetype: %s | Run Nonce: %s",
        civ_name,
        story_archetype,
        run_nonce,
    )

    system_instruction = (
        "You are an expert ancient historian and viral YouTube Shorts scriptwriter.\n"
        f"MANDATORY TARGET CIVILIZATION FOR THIS RUN: {civ_name}\n"
        f"VISUAL MOTIFS TO WEAVE INTO SCENES: {civ_motifs}\n"
        f"MANDATORY STORY ARCHETYPE: {story_archetype}\n"
        f"MANDATORY RECURRING MASCOT CHARACTER IN EVERY VIDEO: {BHOLU_CHARACTER_PROMPT}\n"
        "Bholu is our beloved time-traveling pink teddy bear mascot who appears right alongside the historical characters in every scene!\n\n"
        "CRITICAL DEDUPLICATION & UNIQUENESS RULES:\n"
        "1. Never repeat or overlap with any of these previously covered topics:\n"
        f"{recent_topics_str}\n"
        "2. Do NOT pick overused clichés (no Trojan Horse, no Julius Caesar assassination, no Queen Amanirenas head of Augustus, no 300 Spartans).\n"
        "3. Every single scene in `scenes` MUST include Bholu (the cute fluffy pink teddy bear with red white-spotted inner ears and a red bow tie with white hearts) reacting to or participating in the historical moment, and depict a completely different location, camera angle, character action, and color mood so that no two frames or scenes in the video look similar.\n"
        "   - Scene 1: Wide establishing shot of the setting and hook with Bholu arriving.\n"
        "   - Scene 2: Low-angle medium shot introducing the central character or problem alongside Bholu.\n"
        "   - Scene 3: Close-up dramatic reaction or intricate detail shot featuring Bholu.\n"
        "   - Scene 4: Dynamic action shot from an over-the-shoulder or diagonal perspective.\n"
        "   - Scene 5: High-tension climax shot with dramatic lighting.\n"
        "   - Scene 6 (optional): Sweeping aftermath reveal shot.\n\n"
        "OUTPUT REQUIREMENTS:\n"
        "1. `topic`: Exact historical event name and approximate year.\n"
        "2. `youtube_title`: Catchy hook under 90 characters total, ending with `#shorts #ancienthistory`.\n"
        "3. `youtube_description`: Engaging 2-sentence summary mentioning Bholu's time-travel adventure followed by 5 to 8 relevant hashtags "
        "(including `#shorts`, `#history`, `#ancienthistory`, `#bholu`).\n"
        "4. `scenes`: 5 to 7 scenes designed for a 35 to 50 second video (85 to 125 words total across all scenes).\n"
        "   - `narration`: 1 to 2 punchy, dramatic sentences of spoken voiceover text.\n"
        "   - `visual_prompt`: Detailed, unique visual description of the scene's specific camera angle, characters, Bholu the pink teddy bear with his red heart bow tie, costumes, lighting, and background, "
        f"prefixed verbatim with: \"{CARTOON_STYLE_PREFIX}\""
    )

    user_prompt = (
        f"[Run Entropy ID: {run_nonce}] "
        f"Generate a brand-new, historically accurate, viral Ancient History YouTube Short script "
        f"set in {civ_name} focusing on {story_archetype}. "
        "Ensure every scene has a radically distinct visual composition and camera angle. Output strict JSON."
    )

    candidate_models = [GEMINI_MODEL]
    for fallback_model in ("gemini-3.8-flash", "gemini-3.5-flash-lite"):
        if fallback_model not in candidate_models:
            candidate_models.append(fallback_model)

    last_error = None
    for idx, api_key in enumerate(api_keys, start=1):
        client = genai.Client(api_key=api_key)
        for model_name in candidate_models:
            try:
                logger.info(
                    "Requesting script from Gemini model '%s' (key %d/%d)...",
                    model_name,
                    idx,
                    len(api_keys),
                )
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=ScriptSchema,
                        temperature=0.95,
                    ),
                )
                raw_text = response.text
                if not raw_text:
                    raise ValueError("Empty response received from Gemini API.")
                parsed = json.loads(raw_text)
                validated = ScriptSchema.model_validate(parsed)
                return _normalize_script_payload(validated.model_dump())
            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                logger.warning(
                    "Gemini API attempt (key %d/%d, model '%s') failed: %s",
                    idx,
                    len(api_keys),
                    model_name,
                    exc,
                )
                if "402" in err_str or "RESOURCE_EXHAUSTED" in err_str or "API_KEY_INVALID" in err_str:
                    break

    raise RuntimeError(
        f"All Gemini API key attempts failed. Last error: {last_error}"
    ) from last_error
