"""Seed realistic demo discharge records through the real API.

Run:  python scripts/seed_demo_data.py

Creates ~18 records across common paediatric nursing-home presentations
(Mahavir Nursing Home, Dr. Mitesh Shah) with deliberately varied wording
for the same underlying conditions, so the similar-case recommender can
be evaluated on more than exact text.
Safe to re-run: it skips seeding if any seeded patient already exists.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import auth, config, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402

# (patient, record) pairs. Phrasing intentionally varies within a family.
CASES = [
    # --- Gastroenteritis family
    dict(
        patient=dict(name="Ramesh Pawar", sex="M", dob="2020-06-02"),
        record=dict(
            age_at_admission="5 y", ward="GW/1", weight="18 kg", height="108 cm",
            admission_date="2026-05-03T21:00:00", discharge_date="2026-05-05T10:00:00",
            diagnosis="Acute gastroenteritis with moderate dehydration",
            history="Loose stools 10-12 per day, vomiting, cramping abdominal pain\n\nNo comorbidities",
            temperature="100.2 F", pulse="102/min", bp="104/68", spo2="98%",
            course_in_hospital="IV fluids and antiemetics, improved by day 2",
            advice="ORS after each loose stool, light home food",
            treatment_items=[
                dict(category="hospital", drug="IV RL", dose="1 L", route="IV", frequency="8 hourly", duration="2 days"),
                dict(category="discharge", drug="Tab Ofloxacin-Ornidazole", dose="200/500 mg", route="PO", frequency="1-0-1", duration="5 days", instructions="After food"),
                dict(category="discharge", drug="ORS sachet", dose="1 sachet in 1 L", route="PO", frequency="After each loose stool", duration="Till stools normal"),
                dict(category="discharge", drug="Tab Ondansetron", dose="4 mg", route="PO", frequency="SOS", duration="3 days"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Kavita Bhosale", sex="F", dob="2022-01-15"),
        record=dict(
            age_at_admission="4 y", ward="GW/4", weight="16 kg", height="102 cm",
            admission_date="2026-06-11T18:30:00", discharge_date="2026-06-13T09:00:00",
            diagnosis="Acute diarrhoeal illness, likely food borne",
            history="Frequent watery motions since morning, nausea, giddiness\n\nAte street-food snacks the previous evening",
            temperature="99.6 F", pulse="96/min", bp="100/70", spo2="99%",
            course_in_hospital="Rehydrated with IV fluids, symptomatic care",
            advice="Boiled water, curd rice diet, hand hygiene",
            treatment_items=[
                dict(category="hospital", drug="IV NS", dose="1 L", route="IV", frequency="6 hourly", duration="1 day"),
                dict(category="discharge", drug="Cap Doxycycline", dose="100 mg", route="PO", frequency="1-0-1", duration="3 days"),
                dict(category="discharge", drug="Tab Racecadotril", dose="100 mg", route="PO", frequency="1-1-1", duration="3 days"),
                dict(category="discharge", drug="Probiotic sachet", dose="1 sachet", route="PO", frequency="OD", duration="5 days"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Suresh Jagtap", sex="M", dob="2017-11-20"),
        record=dict(
            age_at_admission="8 y", ward="GW/2", weight="24 kg", height="127 cm",
            admission_date="2026-04-20T14:00:00", discharge_date="2026-04-23T11:00:00",
            diagnosis="Food poisoning with dehydration and prerenal azotemia",
            history="Vomiting and loose motions after a wedding meal, decreased urine output\n\nNo comorbidities. Ate at a family wedding function the previous day.",
            temperature="99.0 F", pulse="108/min", bp="96/64", spo2="97%",
            dehydration_signs="yes", pallor="no", icterus="no",
            abdominal_exam="Soft, diffusely tender, no guarding",
            examination_findings="Dry tongue, decreased skin turgor",
            course_in_hospital="Aggressive rehydration, creatinine normalised before discharge",
            advice="Plenty of oral fluids, avoid outside food, review if urine output drops",
            treatment_items=[
                dict(category="hospital", drug="IV RL", dose="1 L", route="IV", frequency="6 hourly", duration="2 days"),
                dict(category="discharge", drug="Tab Norfloxacin-Tinidazole", dose="400/600 mg", route="PO", frequency="1-0-1", duration="5 days", instructions="After food"),
                dict(category="discharge", drug="ORS sachet", dose="1 sachet in 1 L", route="PO", frequency="Liberally", duration="3 days"),
            ],
        ),
    ),
    # --- Pneumonia / LRTI family
    dict(
        patient=dict(name="Mangala Kulkarni", sex="F", dob="2022-03-08"),
        record=dict(
            age_at_admission="3 y", ward="SR/1", weight="14 kg", height="95 cm",
            admission_date="2026-01-12T20:00:00", discharge_date="2026-01-17T10:30:00",
            diagnosis="Left lower lobe pneumonia",
            history="High fever, cough with yellowish sputum, weakness 5 days\n\nNo comorbidities, up to date on immunisations",
            temperature="102.0 F", pulse="110/min", bp="130/80", spo2="93%",
            pallor="no", cyanosis="no",
            respiratory_system="Crepitations left lower zone, reduced air entry",
            cvs_system="S1 S2 normal, no murmur",
            investigations="CXR left lower zone consolidation, WBC 15.8",
            course_in_hospital="IV antibiotics, nebulisation, oxygen for first two days",
            advice="Complete antibiotic course, breathing exercises, review growth at follow-up",
            treatment_items=[
                dict(category="hospital", drug="Inj Ceftriaxone", dose="1 g", route="IV", frequency="BD", duration="4 days"),
                dict(category="hospital", drug="Nebulised Salbutamol", dose="2.5 mg", route="Inhaled", frequency="TDS", duration="3 days"),
                dict(category="discharge", drug="Tab Amoxicillin-Clavulanate", dose="625 mg", route="PO", frequency="1-1-1", duration="5 days", instructions="After food"),
                dict(category="discharge", drug="Tab Ambroxol", dose="30 mg", route="PO", frequency="1-0-1", duration="5 days"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Dattatray Shinde", sex="M", dob="2023-09-30",
                     past_history="Born full term, no NICU admission"),
        record=dict(
            age_at_admission="2 y", ward="SR/2", weight="12 kg", height="86 cm",
            admission_date="2026-02-02T16:00:00", discharge_date="2026-02-06T11:00:00",
            diagnosis="Acute lower respiratory tract infection with bronchiolitis",
            history="Cough, fast breathing, fever, and reduced feeding for 3 days\n\nNo comorbidities. Attends daycare; an older sibling had a similar cough recently.",
            temperature="101.4 F", pulse="98/min", bp="140/86", spo2="94%",
            respiratory_system="Bilateral wheeze and crepitations, mild subcostal recession",
            course_in_hospital="Oxygen support initially, nebulisation and IV antibiotics; afebrile and feeding well by day 3",
            advice="Nasal saline drops for congestion, continue frequent feeds, review if breathing becomes fast or laboured again",
            treatment_items=[
                dict(category="hospital", drug="Inj Ceftriaxone", dose="50 mg/kg", route="IV", frequency="OD", duration="4 days"),
                dict(category="discharge", drug="Syr Cefixime", dose="5 ml", route="PO", frequency="BD", duration="5 days"),
                dict(category="discharge", drug="Nasal saline drops", dose="2 drops each nostril", route="Nasal", frequency="SOS", duration="5 days"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Shobha Gaikwad", sex="F", dob="2016-12-11"),
        record=dict(
            age_at_admission="9 y", ward="GW/5", weight="27 kg", height="132 cm",
            admission_date="2026-03-15T19:00:00", discharge_date="2026-03-18T10:00:00",
            diagnosis="Chest infection with bronchitis",
            history="Cough with sputum and low grade fever one week, chest heaviness\n\nNo comorbidities",
            temperature="100.6 F", pulse="92/min", bp="110/72", spo2="96%",
            course_in_hospital="Oral antibiotics and mucolytics, steady improvement",
            advice="Warm saline gargles, avoid cold exposure",
            treatment_items=[
                dict(category="discharge", drug="Tab Azithromycin", dose="500 mg", route="PO", frequency="0-0-1", duration="5 days", instructions="1 hour before food"),
                dict(category="discharge", drug="Tab Montelukast-Levocetirizine", dose="10/5 mg", route="PO", frequency="0-0-1", duration="10 days"),
            ],
        ),
    ),
    # --- Dengue family
    dict(
        patient=dict(name="Prakash Salunkhe", sex="M", dob="2015-07-25"),
        record=dict(
            age_at_admission="10 y", ward="GW/6", weight="31 kg", height="138 cm",
            admission_date="2026-06-25T17:00:00", discharge_date="2026-06-29T12:00:00",
            diagnosis="Dengue fever with warning signs",
            history="High fever, severe body ache, retro-orbital pain, one episode of gum bleeding\n\nFever in neighbourhood, monsoon season",
            temperature="103.0 F", pulse="100/min", bp="106/70", spo2="98%",
            rash="yes", pallor="no", meningeal_signs="no",
            throat_findings="Mild congestion",
            examination_findings="Petechial rash over forearms, tourniquet test positive",
            investigations="NS1 antigen positive, platelets 68000 lowest, hematocrit stable",
            course_in_hospital="IV fluids per dengue protocol, platelet monitoring twice daily, no transfusion needed",
            advice="No painkillers other than paracetamol, repeat CBC after 2 days, plenty of fluids",
            treatment_items=[
                dict(category="hospital", drug="IV RL", dose="100 ml/hr", route="IV", frequency="Continuous", duration="3 days"),
                dict(category="discharge", drug="Tab Paracetamol", dose="650 mg", route="PO", frequency="SOS fever", duration="5 days", instructions="Max 4 per day"),
                dict(category="discharge", drug="Papaya leaf extract", dose="1 tab", route="PO", frequency="1-1-1", duration="5 days"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Asha Chavan", sex="F", dob="2013-02-18"),
        record=dict(
            age_at_admission="13 y", ward="GW/3", weight="42 kg", height="155 cm",
            admission_date="2026-07-01T15:00:00", discharge_date="2026-07-05T10:00:00",
            diagnosis="Febrile illness with thrombocytopenia, dengue IgM positive",
            history="Fever 4 days, headache, rash over forearms, easy bruising\n\nSeveral classmates at school down with similar fever this week",
            temperature="102.4 F", pulse="96/min", bp="100/66", spo2="99%",
            investigations="Dengue IgM positive, platelet nadir 54000, no bleeding",
            course_in_hospital="Supportive care, platelets recovered to 110000 at discharge",
            advice="Avoid contact sports for two weeks, mosquito precautions at home and school",
            treatment_items=[
                dict(category="hospital", drug="IV NS", dose="75 ml/hr", route="IV", frequency="Continuous", duration="3 days"),
                dict(category="discharge", drug="Tab Paracetamol", dose="500 mg", route="PO", frequency="SOS fever", duration="5 days"),
                dict(category="discharge", drug="Cap B-complex", dose="1 cap", route="PO", frequency="OD", duration="10 days"),
            ],
        ),
    ),
    # --- Typhoid family
    dict(
        patient=dict(name="Vilas Mane", sex="M", dob="2019-04-05"),
        record=dict(
            age_at_admission="7 y", ward="GW/7", weight="22 kg", height="120 cm",
            admission_date="2026-05-18T13:00:00", discharge_date="2026-05-23T11:00:00",
            diagnosis="Enteric fever",
            history="Stepladder fever 8 days, abdominal discomfort, constipation then loose stools\n\nFrequently eats snacks from the school canteen and roadside vendors",
            temperature="103.2 F", pulse="88/min", bp="112/74", spo2="98%",
            investigations="Blood culture Salmonella typhi, Widal 1:320",
            course_in_hospital="IV ceftriaxone 5 days, fever defervescence by day 4",
            advice="Complete oral antibiotics, boiled water only, soft diet 1 week",
            treatment_items=[
                dict(category="hospital", drug="Inj Ceftriaxone", dose="2 g", route="IV", frequency="OD", duration="5 days"),
                dict(category="discharge", drug="Tab Cefixime", dose="400 mg", route="PO", frequency="OD", duration="7 days"),
                dict(category="discharge", drug="Tab Paracetamol", dose="650 mg", route="PO", frequency="SOS fever", duration="5 days"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Sangeeta Patil", sex="F", dob="2014-08-22"),
        record=dict(
            age_at_admission="11 y", ward="GW/2", weight="34 kg", height="144 cm",
            admission_date="2026-03-02T12:00:00", discharge_date="2026-03-07T10:00:00",
            diagnosis="Typhoid fever, Widal positive",
            history="Continuous fever over one week, dull headache, poor appetite, coated tongue\n\nNo comorbidities",
            temperature="102.8 F", pulse="84/min", bp="108/70", spo2="99%",
            investigations="Widal TO 1:160 TH 1:320, mild transaminitis",
            course_in_hospital="IV antibiotics then oral switch, tolerated diet at discharge",
            advice="Hand hygiene, avoid outside food a month, repeat LFT in 2 weeks",
            treatment_items=[
                dict(category="hospital", drug="Inj Ceftriaxone", dose="2 g", route="IV", frequency="OD", duration="4 days"),
                dict(category="discharge", drug="Tab Azithromycin", dose="500 mg", route="PO", frequency="OD", duration="7 days"),
            ],
        ),
    ),
    # --- UTI family
    dict(
        patient=dict(name="Nirmala Joshi", sex="F", dob="2020-10-14",
                     past_history="Recurrent urinary tract infections, referred to paediatric nephrology"),
        record=dict(
            age_at_admission="5 y", ward="SR/3", weight="17 kg", height="107 cm",
            admission_date="2026-02-20T18:00:00", discharge_date="2026-02-24T10:00:00",
            diagnosis="Acute pyelonephritis",
            history="Fever with chills and rigors, right flank pain, burning micturition\n\nPrevious urinary tract infection last year; under evaluation for recurrent UTIs",
            temperature="102.6 F", pulse="104/min", bp="124/78", spo2="97%",
            investigations="Urine RE plenty pus cells, urine culture E. coli, creatinine 1.1",
            course_in_hospital="IV antibiotics per culture, fever settled day 3",
            advice="3 litres fluids daily, complete antibiotics, repeat urine culture after course",
            treatment_items=[
                dict(category="hospital", drug="Inj Piperacillin-Tazobactam", dose="4.5 g", route="IV", frequency="TDS", duration="4 days"),
                dict(category="discharge", drug="Tab Nitrofurantoin", dose="100 mg", route="PO", frequency="1-0-1", duration="7 days", instructions="After food"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Rekha Sawant", sex="F", dob="2020-05-09"),
        record=dict(
            age_at_admission="6 y", ward="GW/8", weight="20 kg", height="114 cm",
            admission_date="2026-06-05T16:00:00", discharge_date="2026-06-08T09:30:00",
            diagnosis="Urinary tract infection with fever",
            history="Painful urination, increased frequency, lower abdominal pain, fever\n\nNo comorbidities",
            temperature="101.0 F", pulse="94/min", bp="116/76", spo2="98%",
            investigations="Urine RE 15-20 pus cells",
            course_in_hospital="IV then oral antibiotics, symptoms resolved",
            advice="Liberal fluids, do not hold urine",
            treatment_items=[
                dict(category="hospital", drug="Inj Ceftriaxone", dose="1 g", route="IV", frequency="BD", duration="2 days"),
                dict(category="discharge", drug="Tab Ciprofloxacin", dose="500 mg", route="PO", frequency="1-0-1", duration="5 days"),
                dict(category="discharge", drug="Syr Citralka", dose="10 ml in water", route="PO", frequency="1-1-1", duration="5 days"),
            ],
        ),
    ),
    # --- Asthma family
    dict(
        patient=dict(name="Abdul Shaikh", sex="M", dob="2017-01-27",
                     chronic_conditions="Bronchial asthma since age 4, on regular inhalers"),
        record=dict(
            age_at_admission="9 y", ward="SR/4", weight="28 kg", height="133 cm",
            admission_date="2026-01-28T22:00:00", discharge_date="2026-01-31T11:00:00",
            diagnosis="Acute exacerbation of bronchial asthma",
            history="Sudden breathlessness at night, audible wheeze, cough, chest tightness\n\nKnown asthmatic since age 4, on inhalers; dust exposure at home",
            temperature="98.8 F", pulse="112/min", bp="134/84", spo2="91%",
            cyanosis="no", pallor="no",
            respiratory_system="Widespread expiratory wheeze both lungs",
            examination_findings="Accessory muscle use at admission, speaking in phrases",
            course_in_hospital="Repeated nebulisation, IV steroids, oxygen first night",
            advice="Regular inhaler technique reviewed, avoid dust triggers, spacer use",
            treatment_items=[
                dict(category="hospital", drug="Nebulised Salbutamol-Ipratropium", dose="2.5/0.5 mg", route="Inhaled", frequency="4 hourly", duration="2 days"),
                dict(category="hospital", drug="Inj Hydrocortisone", dose="100 mg", route="IV", frequency="TDS", duration="2 days"),
                dict(category="discharge", drug="Budesonide-Formoterol inhaler", dose="200/6 mcg", route="Inhaled", frequency="1-0-1", duration="Continue"),
                dict(category="discharge", drug="Tab Prednisolone", dose="30 mg", route="PO", frequency="OD", duration="5 days", instructions="After breakfast, taper as advised"),
            ],
        ),
    ),
    # --- Diabetic ketoacidosis
    dict(
        patient=dict(name="Ganpat Kadam", sex="M", dob="2016-06-16"),
        record=dict(
            age_at_admission="9 y", ward="SR/5", weight="26 kg", height="130 cm",
            admission_date="2026-02-14T20:30:00", discharge_date="2026-02-19T10:00:00",
            diagnosis="Diabetic ketoacidosis, new-onset type 1 diabetes mellitus",
            history="Excessive thirst and urination for two weeks, vomiting, abdominal pain, and fast breathing since yesterday\n\nNo comorbidities. Noticeable weight loss over the preceding month.",
            temperature="98.6 F", pulse="118/min", bp="100/64", spo2="98%",
            investigations="Blood glucose 486 mg/dL, urine ketones 3+, venous pH 7.18, bicarbonate 9 mEq/L, HbA1c 11.2%",
            course_in_hospital="IV fluid resuscitation and IV insulin infusion per DKA protocol, transitioned to subcutaneous insulin once ketosis resolved; started on structured insulin-administration education for the family",
            advice="Continue subcutaneous insulin as charted, home glucose monitoring four times daily, sick-day rules explained to parents",
            treatment_items=[
                dict(category="hospital", drug="IV Normal Saline", dose="per DKA protocol", route="IV", frequency="Continuous", duration="2 days"),
                dict(category="hospital", drug="IV Insulin infusion", dose="0.1 units/kg/hr", route="IV", frequency="Continuous", duration="2 days"),
                dict(category="discharge", drug="Inj Insulin Glargine", dose="per sliding scale", route="SC", frequency="OD", duration="Continue"),
                dict(category="discharge", drug="Inj Insulin Aspart", dose="per carb count", route="SC", frequency="Before meals", duration="Continue"),
            ],
        ),
    ),
    # --- Cellulitis
    dict(
        patient=dict(name="Baban Thorat", sex="M", dob="2016-03-19"),
        record=dict(
            age_at_admission="10 y", ward="GW/9", weight="30 kg", height="138 cm",
            admission_date="2026-04-08T11:00:00", discharge_date="2026-04-12T10:00:00",
            diagnosis="Cellulitis of left leg",
            history="Painful red swelling of left lower leg 3 days, fever\n\nNo comorbidities. Playing barefoot outdoors; a small injury near the ankle a few days prior.",
            temperature="101.2 F", pulse="98/min", bp="128/80", spo2="98%",
            course_in_hospital="IV antibiotics, limb elevation, steady improvement",
            advice="Protective footwear outdoors, daily dressing at clinic",
            treatment_items=[
                dict(category="hospital", drug="Inj Amoxicillin-Clavulanate", dose="1.2 g", route="IV", frequency="TDS", duration="4 days"),
                dict(category="discharge", drug="Tab Amoxicillin-Clavulanate", dose="625 mg", route="PO", frequency="1-1-1", duration="7 days", instructions="After food"),
                dict(category="discharge", drug="Tab Chymoral Forte", dose="1 tab", route="PO", frequency="1-1-1", duration="5 days", instructions="Empty stomach"),
            ],
        ),
    ),
    # --- Febrile seizure
    dict(
        patient=dict(name="Leela Deshpande", sex="F", dob="2023-12-01"),
        record=dict(
            age_at_admission="2 y", ward="SR/6", weight="12.5 kg", height="87 cm",
            admission_date="2026-03-22T09:00:00", discharge_date="2026-03-24T10:00:00",
            diagnosis="Febrile seizure (simple), resolved",
            history="One episode of generalised jerking lasting about two minutes during a high fever, followed by brief drowsiness\n\nNo comorbidities, no prior seizures. Cold and runny nose for the preceding day.",
            temperature="103.4 F", pulse="128/min", bp="92/58", spo2="99%",
            investigations="Blood glucose normal, no further workup indicated for a simple febrile seizure",
            course_in_hospital="Observed for recurrence, fever controlled with antipyretics, remained seizure-free and alert throughout admission",
            advice="Antipyretics for fever above 100.4 F, tepid sponging, seizure first-aid explained to parents, return immediately if a seizure recurs or lasts over five minutes",
            treatment_items=[
                dict(category="discharge", drug="Syr Paracetamol", dose="10-15 mg/kg", route="PO", frequency="SOS", duration="Till fever settles"),
                dict(category="discharge", drug="Syr Ibuprofen", dose="5-10 mg/kg", route="PO", frequency="SOS", duration="Alternate with paracetamol if needed"),
            ],
        ),
    ),
    # --- Viral fever
    dict(
        patient=dict(name="Meena Kharat", sex="F", dob="2021-09-03"),
        record=dict(
            age_at_admission="4 y", ward="GW/10", weight="15 kg", height="101 cm",
            admission_date="2026-07-08T14:00:00", discharge_date="2026-07-10T10:00:00",
            diagnosis="Acute viral fever",
            history="Fever 3 days with body ache and sore throat, no rash\n\nFamily members with similar symptoms",
            temperature="101.8 F", pulse="92/min", bp="110/70", spo2="99%",
            investigations="Dengue NS1 negative, malaria smear negative",
            course_in_hospital="Symptomatic management, fever settled",
            advice="Rest, fluids, review if fever returns",
            treatment_items=[
                dict(category="discharge", drug="Tab Paracetamol", dose="650 mg", route="PO", frequency="1-1-1", duration="3 days"),
                dict(category="discharge", drug="Tab Levocetirizine", dose="5 mg", route="PO", frequency="0-0-1", duration="5 days"),
            ],
        ),
    ),
    # --- Anemia
    dict(
        patient=dict(name="Yamuna Waghmare", sex="F", dob="2023-02-26"),
        record=dict(
            age_at_admission="3 y", ward="GW/11", weight="12 kg", height="91 cm",
            admission_date="2026-05-27T10:00:00", discharge_date="2026-05-30T11:00:00",
            diagnosis="Severe iron deficiency anemia",
            history="Progressive weakness, breathlessness on exertion, pale appearance\n\nPredominantly milk-based diet with limited iron-rich solids; picky eater",
            temperature="98.4 F", pulse="104/min", bp="102/64", spo2="98%",
            pallor="yes", icterus="no",
            cvs_system="Ejection systolic flow murmur",
            examination_findings="Marked pallor of conjunctivae and nail beds",
            investigations="Hb 6.2, microcytic hypochromic picture, ferritin low",
            course_in_hospital="One PCV transfusion, IV iron started, dietary counselling given",
            advice="Iron-rich weaning foods, continue iron syrup for 3 months, review growth and diet at follow-up",
            treatment_items=[
                dict(category="hospital", drug="Inj Iron Sucrose", dose="as per weight-based protocol", route="IV", frequency="Alternate days", duration="3 doses"),
                dict(category="discharge", drug="Syr Ferrous Ascorbate-Folic Acid", dose="5 ml", route="PO", frequency="OD", duration="3 months", instructions="Avoid with tea or milk"),
            ],
        ),
    ),
]


def seed() -> None:
    if config.IS_PRODUCTION:
        sys.exit("Refusing to seed demo data: DISCHARGE_ENV=production.")
    # Every write is attributed to a user, so seeding needs an admin to act
    # as. Create one with scripts/create_user.py --admin first.
    db = SessionLocal()
    try:
        admin = db.scalars(
            select(models.User).where(models.User.role == "admin", models.User.is_active.is_(True))
            .order_by(models.User.id)
        ).first()
    finally:
        db.close()
    if admin is None:
        sys.exit("No admin user exists yet. Run scripts/create_user.py --admin first.")
    app.dependency_overrides[auth.current_user] = lambda: admin
    with TestClient(app, base_url="https://localhost") as client:
        first_name = CASES[0]["patient"]["name"]
        existing = [
            p for p in client.get("/api/patients", params={"q": first_name}).json()
            if p["name"] == first_name
        ]
        if existing:
            print("Seed data already present, nothing to do.")
            return
        for case in CASES:
            presp = client.post("/api/patients", json=case["patient"])
            presp.raise_for_status()
            patient = presp.json()
            payload = dict(case["record"])
            payload["patient_id"] = patient["id"]
            payload["status"] = "final"
            payload["doctor_name"] = payload.get("doctor_name", "Dr. Mitesh Shah")
            rresp = client.post("/api/records", json=payload)
            rresp.raise_for_status()
            print(f"Seeded record {rresp.json()['id']}: {patient['name']} - {payload['diagnosis']}")
        print(f"\nDone: {len(CASES)} records seeded.")


if __name__ == "__main__":
    seed()
