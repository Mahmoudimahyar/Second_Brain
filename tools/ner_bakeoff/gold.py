"""Hand-labeled NER gold for the ADR-022 bake-off — dental-admissions forum text.

Grounded in the real ingested entity universe (DJ-Backup schools/specialties/
programs) and real forum phrasing. Balanced across the cases ADR-022 cares
about, NOT cherry-picked for any model:

  - full official names, common abbreviations (NYU/UCLA/ASDOH/OMFS/AEGD),
  - long multi-word program names (the headline ADR-022 motivation),
  - mentions embedded in prose, multiple entities per sentence,
  - hard negatives (sentences with no dental entity).

Entity types kept coarse (school / specialty / program) because that is what a
zero-shot label set can plausibly distinguish; resolution to a canonical id is a
separate downstream step (the canonical index).
"""

from __future__ import annotations

from dataclasses import dataclass, field

SCHOOL = "dental school"
SPECIALTY = "dental specialty"
PROGRAM = "residency program"

LABELS = [SCHOOL, SPECIALTY, PROGRAM]


@dataclass(frozen=True)
class GoldItem:
    text: str
    spans: list[tuple[str, str]] = field(default_factory=list)  # (surface_text, type)


GOLD: tuple[GoldItem, ...] = (
    # --- full official names ---
    GoldItem("I just got accepted to the University of Pennsylvania School of "
             "Dental Medicine and I'm so relieved.",
             [("University of Pennsylvania School of Dental Medicine", SCHOOL)]),
    GoldItem("Harvard School of Dental Medicine sent interview invites yesterday.",
             [("Harvard School of Dental Medicine", SCHOOL)]),
    GoldItem("Does anyone have stats for Arizona School of Dentistry & Oral Health?",
             [("Arizona School of Dentistry & Oral Health", SCHOOL)]),
    GoldItem("Touro College of Dental Medicine at New York Medical College is new.",
             [("Touro College of Dental Medicine at New York Medical College", SCHOOL)]),
    # --- abbreviations ---
    GoldItem("NYU vs UCLA for cost of attendance — which would you pick?",
             [("NYU", SCHOOL), ("UCLA", SCHOOL)]),
    GoldItem("ASDOH waitlisted me but UCSF rejected me outright.",
             [("ASDOH", SCHOOL), ("UCSF", SCHOOL)]),
    GoldItem("Is Tufts worth the tuition compared to BU?",
             [("Tufts", SCHOOL), ("BU", SCHOOL)]),
    # --- specialties (full + abbrev) ---
    GoldItem("I'm leaning toward Oral and Maxillofacial Surgery over Endodontics.",
             [("Oral and Maxillofacial Surgery", SPECIALTY), ("Endodontics", SPECIALTY)]),
    GoldItem("OMFS is a 6-year track but Perio is only 3.",
             [("OMFS", SPECIALTY), ("Perio", SPECIALTY)]),
    GoldItem("Anyone matched Pediatric Dentistry this cycle? Pedo seems competitive.",
             [("Pediatric Dentistry", SPECIALTY), ("Pedo", SPECIALTY)]),
    GoldItem("Prosthodontics and Periodontics both interest me.",
             [("Prosthodontics", SPECIALTY), ("Periodontics", SPECIALTY)]),
    # --- long program names (the ADR-022 motivation) ---
    GoldItem("I interviewed for the Oral and Maxillofacial Surgery residency at the "
             "University of Pennsylvania last week.",
             [("Oral and Maxillofacial Surgery residency at the University of "
               "Pennsylvania", PROGRAM)]),
    GoldItem("The Advanced Education in General Dentistry program at NYU Langone "
             "Dental Medicine is one year.",
             [("Advanced Education in General Dentistry program at NYU Langone "
               "Dental Medicine", PROGRAM)]),
    GoldItem("Applying to the Pediatric Dentistry residency at Children's Hospital "
             "of Philadelphia this year.",
             [("Pediatric Dentistry residency at Children's Hospital of "
               "Philadelphia", PROGRAM)]),
    GoldItem("The General Practice Residency at the University of Michigan offers a "
             "stipend.",
             [("General Practice Residency at the University of Michigan", PROGRAM)]),
    # --- multiple entity types in one sentence ---
    GoldItem("Between an Endodontics residency at Boston University and Orthodontics "
             "at UCLA, which has better outcomes?",
             [("Endodontics residency at Boston University", PROGRAM),
              ("Orthodontics", SPECIALTY), ("UCLA", SCHOOL)]),
    GoldItem("I shadowed an OMFS surgeon who trained at the University of Iowa.",
             [("OMFS", SPECIALTY), ("University of Iowa", SCHOOL)]),
    # --- embedded in longer prose ---
    GoldItem("After two gap years and a postbacc, I finally got off the waitlist at "
             "Midwestern University College of Dental Medicine in Arizona.",
             [("Midwestern University College of Dental Medicine in Arizona", SCHOOL)]),
    GoldItem("Honestly the Loma Linda University School of Dentistry secondary was "
             "the longest one I filled out.",
             [("Loma Linda University School of Dentistry", SCHOOL)]),
    GoldItem("My mentor said the Prosthodontics program at the University of "
             "Washington is underrated.",
             [("Prosthodontics program at the University of Washington", PROGRAM)]),
    # --- hard negatives (no dental entity) ---
    GoldItem("I studied for the DAT for three months using Bootcamp and Anki.", []),
    GoldItem("Honestly the legality of that varies state by state.", []),
    GoldItem("My GPA is a 3.6 and I have 200 shadowing hours, am I competitive?", []),
    GoldItem("Wikipedia is more useful than half my textbooks tbh.", []),
    # --- typo / casual forms ---
    GoldItem("anyone else applying to ohio state dental or u of michigan?",
             [("ohio state dental", SCHOOL), ("u of michigan", SCHOOL)]),
    GoldItem("waitlisted at penn, accepted at temple, rejected from columbia.",
             [("penn", SCHOOL), ("temple", SCHOOL), ("columbia", SCHOOL)]),
)
