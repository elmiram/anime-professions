"""Extraction lexicon: ISCO-08 unit code -> surface forms + ambiguity flag.

Design (see PROJECT_PLAN.md §5):
  * Membership in LEXICON == the unit group is `renderable` (plausibly named in anime).
    Every ISCO unit group NOT here is `not_renderable`: a zero count for it means
    "untestable", not "absent from anime".
  * `ambiguous=True` routes candidate sentences to the Stage-2 LLM adjudicator. Set it
    generously for cross-domain polysemy ("pilot" = aircraft vs mecha vs TV pilot;
    "officer"; "band"). Unambiguous terms (pharmacist, veterinarian, blacksmith) skip
    the LLM and are trusted from Stage 1.
  * Prefer disambiguating MULTI-WORD forms at Stage 1 ("software engineer", "police
    officer") over bare polysemous words, so fewer candidates need the LLM.
  * Where anime text can't resolve an ISCO sub-split (e.g. teacher level), a surface term
    maps to the MODAL unit group and the choice is recorded in NOTES; trust it at the
    roll-up level. Precision/recall measurement flags any that misbehave.

Terms are matched case-insensitively on word boundaries over source text.
"""
from __future__ import annotations

# code -> (surface_forms, ambiguous)
LEXICON: dict[str, tuple[tuple[str, ...], bool]] = {
    # ---- Major 1: Managers ------------------------------------------------
    "1113": (("village chief", "tribal chief"), True),
    "1120": (("ceo", "chief executive", "company president", "executive director"), True),
    "1221": (("sales manager", "marketing manager"), False),
    "1411": (("hotel manager", "innkeeper", "inn manager"), False),
    "1412": (("restaurant manager", "restaurant owner"), False),
    "1420": (("store manager", "shop manager", "shopkeeper", "store owner"), True),

    # ---- Major 2: Professionals -------------------------------------------
    "2111": (("astronomer", "physicist"), False),
    "2113": (("chemist",), True),                      # chemist = pharmacist in BrE
    "2131": (("biologist", "zoologist", "botanist"), False),
    "2141": (("industrial engineer",), False),
    "2142": (("civil engineer",), False),
    "2144": (("mechanical engineer",), False),
    "2149": (("robotics engineer",), False),
    "2151": (("electrical engineer",), False),
    "2152": (("electronics engineer",), False),
    "2161": (("architect",), True),                    # "architect of the plan" (metaphor)
    "2166": (("illustrator", "graphic designer", "designer"), True),
    "2211": (("doctor", "physician", "gp", "general practitioner"), True),
    "2212": (("surgeon", "specialist doctor", "psychiatrist", "cardiologist"), True),
    "2221": (("nurse",), True),                        # verb "to nurse", wet nurse
    "2250": (("veterinarian", "vet", "veterinary surgeon"), True),   # "vet" = veteran
    "2261": (("dentist",), False),
    "2262": (("pharmacist", "apothecary", "druggist"), False),
    "2265": (("dietician", "nutritionist"), False),
    "2310": (("professor", "university lecturer", "university teacher"), True),  # "professor" nickname
    "2330": (("teacher", "schoolteacher", "high school teacher", "homeroom teacher"), True),
    "2341": (("primary school teacher", "elementary school teacher"), False),
    "2342": (("kindergarten teacher", "preschool teacher", "nursery teacher"), False),
    "2411": (("accountant", "bookkeeper", "auditor"), False),
    "2413": (("financial analyst", "financial planner"), False),
    "2423": (("hr manager", "recruiter", "personnel officer"), True),
    "2431": (("advertising executive", "ad executive", "marketer"), False),
    "2432": (("public relations officer", "pr rep", "publicist"), False),
    "2511": (("systems analyst",), False),
    "2512": (("software developer", "software engineer", "programmer", "coder", "game developer"), True),
    "2513": (("web developer", "web designer"), False),
    "2611": (("lawyer", "attorney", "barrister", "solicitor", "prosecutor", "defense attorney"), True),
    "2612": (("judge", "magistrate"), True),           # "judge" verb / competition judge
    "2621": (("archivist", "curator", "museum curator"), True),
    "2622": (("librarian",), False),
    "2631": (("economist",), False),
    "2634": (("psychologist", "therapist", "counselor", "counsellor"), True),
    "2635": (("social worker", "caseworker"), False),
    "2636": (("priest", "monk", "nun", "clergyman", "pastor", "chaplain", "bishop", "shrine priest"), True),
    "2641": (("novelist", "author", "writer", "manga artist", "mangaka", "screenwriter", "playwright"), True),
    "2642": (("journalist", "reporter", "news reporter", "correspondent"), True),
    "2643": (("translator", "interpreter"), True),     # "interpreter" of dreams etc
    "2651": (("painter", "artist", "sculptor"), True),  # painter = house painter; artist broad
    "2652": (("musician", "singer", "composer", "pianist", "violinist", "guitarist"), True),
    "2653": (("dancer", "ballerina", "choreographer"), True),
    "2654": (("film director", "movie director", "film producer", "stage director"), True),
    "2655": (("actor", "actress", "voice actor", "voice actress", "seiyuu"), True),
    "2656": (("announcer", "newscaster", "radio host", "tv host", "commentator"), True),
    "2659": (("idol", "pop idol", "entertainer"), True),   # idol: modal creative-performer bucket

    # ---- Major 3: Technicians & associate professionals -------------------
    "3141": (("lab technician", "laboratory technician"), False),
    "3151": (("ship engineer", "ship's engineer"), False),
    "3153": (("pilot", "aircraft pilot", "aviator", "fighter pilot", "airline pilot"), True),  # mecha/TV pilot
    "3221": (("nurse practitioner", "assistant nurse"), True),
    "3240": (("veterinary technician", "vet tech"), False),
    "3251": (("dental hygienist", "dental assistant"), False),
    "3258": (("paramedic", "ambulance worker", "emt"), False),
    "3311": (("stockbroker", "trader", "securities dealer", "day trader"), True),  # trader broad
    "3313": (("bookkeeper",), False),
    "3321": (("insurance agent", "insurance representative", "insurance broker", "insurance salesman"), False),
    "3322": (("sales representative", "salesman", "saleswoman", "salesperson"), True),
    "3343": (("executive secretary", "personal assistant", "administrative assistant"), True),
    "3355": (("detective", "police detective", "police inspector", "investigator"), True),  # private/fantasy
    "3421": (("athlete", "professional athlete", "sportsman", "baseball player", "soccer player"), True),
    "3422": (("coach", "sports coach", "trainer", "manager"), True),   # coach/manager/trainer polysemy
    "3423": (("fitness instructor", "personal trainer", "gym instructor"), False),
    "3431": (("photographer",), True),                 # sniper "shot"? mild; photog usually clear
    "3432": (("interior designer", "decorator"), False),
    "3434": (("chef", "head chef", "pastry chef", "sous chef"), True),   # chef metaphor
    "3511": (("it technician", "systems administrator", "sysadmin"), False),
    "3521": (("cameraman", "broadcast technician", "sound engineer"), True),

    # ---- Major 4: Clerical support ----------------------------------------
    "4110": (("office worker", "office clerk", "salaryman", "office lady", "clerk"), True),
    "4120": (("secretary",), True),                    # secretary of state / club secretary
    "4211": (("bank teller", "bank clerk"), False),
    "4212": (("croupier", "casino dealer"), False),
    "4221": (("travel agent",), False),
    "4222": (("call centre worker", "call center operator"), False),
    "4224": (("hotel receptionist", "front desk clerk"), False),
    "4226": (("receptionist",), False),
    "4412": (("mail carrier", "postman", "mailman", "postal worker"), False),

    # ---- Major 5: Service and sales ---------------------------------------
    "5111": (("flight attendant", "stewardess", "cabin crew", "air hostess"), False),
    "5113": (("tour guide", "tour conductor"), True),  # "guide" broad
    "5120": (("cook", "line cook", "ramen cook"), True),  # cook verb
    "5131": (("waiter", "waitress", "server"), True),   # server = computer server
    "5132": (("bartender", "barkeep"), False),
    "5141": (("hairdresser", "hairstylist", "barber"), False),
    "5142": (("beautician", "cosmetologist", "makeup artist"), False),
    "5152": (("butler", "housekeeper", "steward"), True),   # steward polysemy
    "5164": (("pet groomer", "dog groomer"), False),
    "5165": (("driving instructor",), False),
    "5211": (("market vendor", "stall vendor", "market stall owner"), False),
    "5212": (("street food vendor", "food cart vendor"), False),
    "5221": (("shopkeeper", "store clerk", "shop owner"), True),
    "5223": (("shop assistant", "sales clerk", "sales assistant", "shop staff"), True),
    "5230": (("cashier", "checkout clerk"), False),
    "5241": (("model", "fashion model", "runway model"), True),   # model = role model / model kit
    "5245": (("gas station attendant", "service station attendant"), False),
    "5246": (("barista", "cafe worker", "counter attendant"), True),  # cafe worker broad
    "5311": (("babysitter", "nanny", "childcare worker"), False),
    "5321": (("care worker", "health care assistant", "orderly"), True),
    "5322": (("caregiver", "caretaker", "home carer"), True),   # caretaker = janitor/guardian
    "5329": (("nursing home worker",), False),
    "5411": (("firefighter", "fireman"), False),
    "5412": (("police officer", "policeman", "policewoman", "cop", "patrol officer", "beat cop"), True),
    "5413": (("prison guard", "prison warden", "jailer"), False),
    "5414": (("security guard", "bodyguard", "night watchman"), True),  # bodyguard/guard broad
    "5419": (("bouncer",), True),

    # ---- Major 6: Skilled agricultural / forestry / fishery ---------------
    "6111": (("farmer", "rice farmer", "crop farmer"), True),   # "farmer" broad/idiom
    "6113": (("gardener", "horticulturist"), True),
    "6121": (("rancher", "cattle farmer", "dairy farmer", "livestock farmer"), False),
    "6210": (("logger", "lumberjack", "forester"), False),
    "6222": (("fisherman", "fisher", "fisherwoman", "angler"), True),   # angler = anglerfish?/verb

    # ---- Major 7: Craft and related trades --------------------------------
    "7111": (("house builder", "home builder"), False),
    "7115": (("carpenter", "joiner", "woodworker"), False),
    "7126": (("plumber", "pipefitter"), False),
    "7212": (("welder",), False),
    "7221": (("blacksmith", "smith", "farrier"), True),    # "smith" as surname
    "7231": (("mechanic", "auto mechanic", "car mechanic", "repairman"), True),
    "7234": (("bicycle repairer", "bike mechanic"), False),
    "7311": (("watchmaker", "clockmaker", "instrument maker"), False),
    "7312": (("instrument maker", "piano tuner", "luthier"), False),
    "7313": (("jeweller", "jeweler", "goldsmith"), False),
    "7314": (("potter", "ceramicist"), True),          # Potter as surname
    "7317": (("craftsman", "artisan", "woodcarver"), True),
    "7322": (("printer", "print worker"), True),       # printer = machine
    "7411": (("electrician",), False),
    "7511": (("butcher", "fishmonger"), True),         # "butcher" verb/idiom
    "7512": (("baker", "pastry cook", "confectioner"), False),
    "7531": (("tailor", "seamstress", "dressmaker", "furrier"), False),
    "7536": (("shoemaker", "cobbler"), False),

    # ---- Major 8: Plant and machine operators / assemblers ----------------
    "8111": (("miner", "coal miner"), True),           # "miner" = minor typo/data-miner
    "8311": (("train driver", "locomotive engineer", "train conductor"), True),
    "8321": (("motorcycle courier", "biker"), True),
    "8322": (("taxi driver", "cab driver", "chauffeur", "driver"), True),   # driver broad
    "8331": (("bus driver", "tram driver"), False),
    "8332": (("truck driver", "trucker", "lorry driver"), False),
    "8350": (("sailor", "deckhand", "ship's crew"), True),   # sailor moon / navy sailor

    # ---- Major 9: Elementary occupations ----------------------------------
    "9111": (("maid", "housemaid", "domestic servant"), True),   # maid cafe / maid outfit
    "9112": (("cleaner", "janitor", "custodian"), True),   # "clean" verb noise
    "9313": (("construction worker", "day laborer", "builder"), True),
    "9411": (("fast food worker",), False),
    "9412": (("kitchen helper", "dishwasher", "kitchen hand"), True),  # dishwasher = appliance
    "9520": (("street vendor", "peddler", "hawker"), True),
    "9621": (("courier", "delivery driver", "delivery boy", "messenger"), True),   # messenger broad

    # ---- Major 0: Armed forces --------------------------------------------
    "0110": (("military officer", "army officer", "naval officer", "commanding officer", "colonel"), True),
    "0310": (("soldier", "infantryman", "serviceman", "enlisted soldier"), True),  # "soldier on" idiom
}

# Non-obvious modal mapping choices, surfaced in the output so they can be audited.
NOTES: dict[str, str] = {
    "2330": "Bare 'teacher' -> modal secondary-school teacher; most anime teachers are high-school. Trust at minor-group 23x roll-up.",
    "2659": "'idol' mapped to creative/performing artists nec as the modal J-idol bucket.",
    "3422": "'manager' here is sports/talent manager; company managers are Major 1. Ambiguous -> adjudicated.",
    "5412": "Bare police terms; 'officer' alone is deliberately excluded (too polysemous). Detectives are 3355.",
    "9111": "'maid' -> domestic cleaners/helpers; live-in 'butler'/'housekeeper' are 5152.",
    "2641": "'manga artist'/'mangaka' grouped with authors/writers (story creators).",
}

# ---- Fantasy stratum (kept entirely separate; NEVER folded into ISCO) -----
# name -> (surface_forms, ambiguous_with_real_occupation)
FANTASY: dict[str, tuple[tuple[str, ...], bool]] = {
    "ninja":         (("ninja", "shinobi", "kunoichi"), False),
    "samurai":       (("samurai", "ronin"), True),          # historical real vs fantasy
    "mercenary":     (("mercenary", "sellsword"), True),    # real trade vs fantasy party role
    "assassin":      (("assassin", "hitman"), True),        # real crime vs fantasy class
    "bounty_hunter": (("bounty hunter",), True),
    "pirate":        (("pirate", "buccaneer"), True),
    "yakuza":        (("yakuza", "gangster", "mobster"), True),
    "knight":        (("knight", "paladin"), False),
    "adventurer":    (("adventurer", "guild member"), False),
    "mage":          (("mage", "wizard", "sorcerer", "witch", "magician"), False),
    "exorcist":      (("exorcist", "demon slayer", "demon hunter"), False),
    "shrine_maiden": (("shrine maiden", "miko", "priestess"), False),
    "hero":          (("hero", "chosen one"), True),        # "hero" is broad/metaphorical
    "shinigami":     (("shinigami", "death god", "grim reaper", "reaper"), False),
    "royalty":       (("prince", "princess", "king", "queen", "emperor", "empress"), True),
    "noble":         (("noble", "aristocrat", "duke", "baron", "viscount", "marquis"), True),
    "monster_hunter": (("monster hunter", "beast hunter", "slayer"), True),
    "summoner":      (("summoner", "beastmaster", "tamer"), False),
    "alchemist":     (("alchemist",), True),               # historical real vs fantasy
    "vampire_hunter": (("vampire hunter",), False),
}
