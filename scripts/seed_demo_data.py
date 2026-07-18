"""Seed realistic demo discharge records through the real API.

Run:  python scripts/seed_demo_data.py

Creates ~18 records across common nursing-home presentations with
deliberately varied wording for the same underlying conditions, so the
similar-case recommender can be evaluated on more than exact text.
Safe to re-run: it skips seeding if any seeded patient already exists.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# (patient, record) pairs. Phrasing intentionally varies within a family.
CASES = [
    # --- Gastroenteritis family
    dict(
        patient=dict(name="Ramesh Pawar", sex="M", dob="1985-06-02", phone="9822011001"),
        record=dict(
            age_at_admission="41 y", ward_bed="GW/1",
            admission_date="2026-05-03T21:00:00", discharge_date="2026-05-05T10:00:00",
            diagnosis="Acute gastroenteritis with moderate dehydration",
            presenting_complaints="Loose stools 10-12 per day, vomiting, cramping abdominal pain",
            history="No comorbidities",
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
        patient=dict(name="Kavita Bhosale", sex="F", dob="1993-01-15", phone="9822011002"),
        record=dict(
            age_at_admission="33 y", ward_bed="GW/4",
            admission_date="2026-06-11T18:30:00", discharge_date="2026-06-13T09:00:00",
            diagnosis="Acute diarrhoeal illness, likely food borne",
            presenting_complaints="Frequent watery motions since morning, nausea, giddiness",
            history="Ate outside food previous night",
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
        patient=dict(name="Suresh Jagtap", sex="M", dob="1958-11-20", phone="9822011003"),
        record=dict(
            age_at_admission="67 y", ward_bed="GW/2",
            admission_date="2026-04-20T14:00:00", discharge_date="2026-04-23T11:00:00",
            diagnosis="Food poisoning with dehydration and prerenal azotemia",
            presenting_complaints="Vomiting and loose motions after a wedding meal, decreased urine output",
            history="Hypertensive on amlodipine",
            temperature="99.0 F", pulse="108/min", bp="96/64", spo2="97%",
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
        patient=dict(name="Mangala Kulkarni", sex="F", dob="1961-03-08", phone="9822011004"),
        record=dict(
            age_at_admission="65 y", ward_bed="SR/1",
            admission_date="2026-01-12T20:00:00", discharge_date="2026-01-17T10:30:00",
            diagnosis="Left lower lobe pneumonia",
            presenting_complaints="High fever, cough with yellowish sputum, weakness 5 days",
            history="Diabetic on oral hypoglycemics",
            temperature="102.0 F", pulse="110/min", bp="130/80", spo2="93%",
            investigations="CXR left lower zone consolidation, WBC 15.8",
            course_in_hospital="IV antibiotics, nebulisation, oxygen for first two days",
            advice="Complete antibiotic course, breathing exercises, sugar monitoring",
            treatment_items=[
                dict(category="hospital", drug="Inj Ceftriaxone", dose="1 g", route="IV", frequency="BD", duration="4 days"),
                dict(category="hospital", drug="Nebulised Salbutamol", dose="2.5 mg", route="Inhaled", frequency="TDS", duration="3 days"),
                dict(category="discharge", drug="Tab Amoxicillin-Clavulanate", dose="625 mg", route="PO", frequency="1-1-1", duration="5 days", instructions="After food"),
                dict(category="discharge", drug="Tab Ambroxol", dose="30 mg", route="PO", frequency="1-0-1", duration="5 days"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Dattatray Shinde", sex="M", dob="1950-09-30", phone="9822011005"),
        record=dict(
            age_at_admission="75 y", ward_bed="SR/2",
            admission_date="2026-02-02T16:00:00", discharge_date="2026-02-06T11:00:00",
            diagnosis="Lower respiratory tract infection in an elderly smoker",
            presenting_complaints="Productive cough, fever with chills, reduced appetite",
            history="Chronic smoker 40 years, old pulmonary TB treated 2005",
            temperature="101.4 F", pulse="98/min", bp="140/86", spo2="94%",
            course_in_hospital="IV antibiotics and chest physiotherapy, afebrile from day 3",
            advice="Stop smoking counselling given, steam inhalation, high protein diet",
            treatment_items=[
                dict(category="hospital", drug="Inj Piperacillin-Tazobactam", dose="4.5 g", route="IV", frequency="TDS", duration="4 days"),
                dict(category="discharge", drug="Tab Cefixime", dose="200 mg", route="PO", frequency="1-0-1", duration="5 days"),
                dict(category="discharge", drug="Syr Grilinctus", dose="10 ml", route="PO", frequency="1-1-1", duration="5 days"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Shobha Gaikwad", sex="F", dob="1988-12-11", phone="9822011006"),
        record=dict(
            age_at_admission="37 y", ward_bed="GW/5",
            admission_date="2026-03-15T19:00:00", discharge_date="2026-03-18T10:00:00",
            diagnosis="Chest infection with bronchitis",
            presenting_complaints="Cough with sputum and low grade fever one week, chest heaviness",
            history="No comorbidities",
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
        patient=dict(name="Prakash Salunkhe", sex="M", dob="1997-07-25", phone="9822011007"),
        record=dict(
            age_at_admission="28 y", ward_bed="GW/6",
            admission_date="2026-06-25T17:00:00", discharge_date="2026-06-29T12:00:00",
            diagnosis="Dengue fever with warning signs",
            presenting_complaints="High fever, severe body ache, retro-orbital pain, one episode of gum bleeding",
            history="Fever in neighbourhood, monsoon season",
            temperature="103.0 F", pulse="100/min", bp="106/70", spo2="98%",
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
        patient=dict(name="Asha Chavan", sex="F", dob="2002-02-18", phone="9822011008"),
        record=dict(
            age_at_admission="24 y", ward_bed="GW/3",
            admission_date="2026-07-01T15:00:00", discharge_date="2026-07-05T10:00:00",
            diagnosis="Febrile illness with thrombocytopenia, dengue IgM positive",
            presenting_complaints="Fever 4 days, headache, rash over forearms, easy bruising",
            history="College hostel resident, several similar cases nearby",
            temperature="102.4 F", pulse="96/min", bp="100/66", spo2="99%",
            investigations="Dengue IgM positive, platelet nadir 54000, no bleeding",
            course_in_hospital="Supportive care, platelets recovered to 110000 at discharge",
            advice="Avoid contact sports two weeks, mosquito precautions at hostel",
            treatment_items=[
                dict(category="hospital", drug="IV NS", dose="75 ml/hr", route="IV", frequency="Continuous", duration="3 days"),
                dict(category="discharge", drug="Tab Paracetamol", dose="500 mg", route="PO", frequency="SOS fever", duration="5 days"),
                dict(category="discharge", drug="Cap B-complex", dose="1 cap", route="PO", frequency="OD", duration="10 days"),
            ],
        ),
    ),
    # --- Typhoid family
    dict(
        patient=dict(name="Vilas Mane", sex="M", dob="1990-04-05", phone="9822011009"),
        record=dict(
            age_at_admission="36 y", ward_bed="GW/7",
            admission_date="2026-05-18T13:00:00", discharge_date="2026-05-23T11:00:00",
            diagnosis="Enteric fever",
            presenting_complaints="Stepladder fever 8 days, abdominal discomfort, constipation then loose stools",
            history="Frequent meals at roadside stalls",
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
        patient=dict(name="Sangeeta Patil", sex="F", dob="1984-08-22", phone="9822011010"),
        record=dict(
            age_at_admission="41 y", ward_bed="GW/2",
            admission_date="2026-03-02T12:00:00", discharge_date="2026-03-07T10:00:00",
            diagnosis="Typhoid fever, Widal positive",
            presenting_complaints="Continuous fever over one week, dull headache, poor appetite, coated tongue",
            history="No comorbidities",
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
        patient=dict(name="Nirmala Joshi", sex="F", dob="1954-10-14", phone="9822011011"),
        record=dict(
            age_at_admission="71 y", ward_bed="SR/3",
            admission_date="2026-02-20T18:00:00", discharge_date="2026-02-24T10:00:00",
            diagnosis="Acute pyelonephritis",
            presenting_complaints="Fever with chills and rigors, right flank pain, burning micturition",
            history="Diabetic 15 years, previous UTI last year",
            temperature="102.6 F", pulse="104/min", bp="124/78", spo2="97%",
            investigations="Urine RE plenty pus cells, urine culture E. coli, creatinine 1.1",
            course_in_hospital="IV antibiotics per culture, fever settled day 3",
            advice="3 litres fluids daily, complete antibiotics, sugar control, repeat urine culture after course",
            treatment_items=[
                dict(category="hospital", drug="Inj Piperacillin-Tazobactam", dose="4.5 g", route="IV", frequency="TDS", duration="4 days"),
                dict(category="discharge", drug="Tab Nitrofurantoin", dose="100 mg", route="PO", frequency="1-0-1", duration="7 days", instructions="After food"),
            ],
        ),
    ),
    dict(
        patient=dict(name="Rekha Sawant", sex="F", dob="1979-05-09", phone="9822011012"),
        record=dict(
            age_at_admission="47 y", ward_bed="GW/8",
            admission_date="2026-06-05T16:00:00", discharge_date="2026-06-08T09:30:00",
            diagnosis="Urinary tract infection with fever",
            presenting_complaints="Painful urination, increased frequency, lower abdominal pain, fever",
            history="No comorbidities",
            temperature="101.0 F", pulse="94/min", bp="116/76", spo2="98%",
            investigations="Urine RE 15-20 pus cells",
            course_in_hospital="IV then oral antibiotics, symptoms resolved",
            advice="Liberal fluids, do not hold urine, cranberry supplement optional",
            treatment_items=[
                dict(category="hospital", drug="Inj Ceftriaxone", dose="1 g", route="IV", frequency="BD", duration="2 days"),
                dict(category="discharge", drug="Tab Ciprofloxacin", dose="500 mg", route="PO", frequency="1-0-1", duration="5 days"),
                dict(category="discharge", drug="Syr Citralka", dose="10 ml in water", route="PO", frequency="1-1-1", duration="5 days"),
            ],
        ),
    ),
    # --- Asthma / COPD family
    dict(
        patient=dict(name="Abdul Shaikh", sex="M", dob="1969-01-27", phone="9822011013"),
        record=dict(
            age_at_admission="57 y", ward_bed="SR/4",
            admission_date="2026-01-28T22:00:00", discharge_date="2026-01-31T11:00:00",
            diagnosis="Acute exacerbation of bronchial asthma",
            presenting_complaints="Sudden breathlessness at night, audible wheeze, cough, chest tightness",
            history="Known asthmatic 20 years on inhalers, dust exposure at work",
            temperature="98.8 F", pulse="112/min", bp="134/84", spo2="91%",
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
    dict(
        patient=dict(name="Ganpat Kadam", sex="M", dob="1948-06-16", phone="9822011014"),
        record=dict(
            age_at_admission="77 y", ward_bed="SR/5",
            admission_date="2026-02-14T20:30:00", discharge_date="2026-02-19T10:00:00",
            diagnosis="Acute exacerbation of COPD",
            presenting_complaints="Increased breathlessness and sputum, unable to complete sentences",
            history="COPD 10 years, ex-beedi smoker, on home inhalers",
            temperature="99.4 F", pulse="106/min", bp="142/88", spo2="88%",
            course_in_hospital="Controlled oxygen, nebulisation, antibiotics, steroids",
            advice="Home breathing exercises, influenza vaccine advised, follow inhaler schedule strictly",
            treatment_items=[
                dict(category="hospital", drug="Nebulised Salbutamol-Ipratropium", dose="2.5/0.5 mg", route="Inhaled", frequency="6 hourly", duration="4 days"),
                dict(category="hospital", drug="Inj Ceftriaxone", dose="1 g", route="IV", frequency="BD", duration="4 days"),
                dict(category="discharge", drug="Tiotropium inhaler", dose="18 mcg", route="Inhaled", frequency="OD", duration="Continue"),
                dict(category="discharge", drug="Tab Doxofylline", dose="400 mg", route="PO", frequency="1-0-1", duration="10 days"),
            ],
        ),
    ),
    # --- Cellulitis
    dict(
        patient=dict(name="Baban Thorat", sex="M", dob="1972-03-19", phone="9822011015"),
        record=dict(
            age_at_admission="54 y", ward_bed="GW/9",
            admission_date="2026-04-08T11:00:00", discharge_date="2026-04-12T10:00:00",
            diagnosis="Cellulitis of left leg",
            presenting_complaints="Painful red swelling of left lower leg 3 days, fever",
            history="Diabetic, barefoot farm work, small injury near ankle",
            temperature="101.2 F", pulse="98/min", bp="128/80", spo2="98%",
            course_in_hospital="IV antibiotics, limb elevation, sugars optimised",
            advice="Protective footwear always, daily dressing at clinic, sugar control",
            treatment_items=[
                dict(category="hospital", drug="Inj Amoxicillin-Clavulanate", dose="1.2 g", route="IV", frequency="TDS", duration="4 days"),
                dict(category="discharge", drug="Tab Amoxicillin-Clavulanate", dose="625 mg", route="PO", frequency="1-1-1", duration="7 days", instructions="After food"),
                dict(category="discharge", drug="Tab Chymoral Forte", dose="1 tab", route="PO", frequency="1-1-1", duration="5 days", instructions="Empty stomach"),
            ],
        ),
    ),
    # --- Hypertensive urgency
    dict(
        patient=dict(name="Leela Deshpande", sex="F", dob="1957-12-01", phone="9822011016"),
        record=dict(
            age_at_admission="68 y", ward_bed="SR/6",
            admission_date="2026-03-22T09:00:00", discharge_date="2026-03-24T10:00:00",
            diagnosis="Hypertensive urgency",
            presenting_complaints="Severe headache and giddiness, BP 200/110 at home check",
            history="Hypertensive, stopped medicines on her own 2 months ago",
            temperature="98.6 F", pulse="88/min", bp="196/108", spo2="98%",
            course_in_hospital="Gradual BP control with oral agents, counselled on adherence",
            advice="Never stop BP medicines without advice, home BP diary twice daily, low salt diet",
            treatment_items=[
                dict(category="discharge", drug="Tab Telmisartan-Amlodipine", dose="40/5 mg", route="PO", frequency="1-0-0", duration="Continue"),
                dict(category="discharge", drug="Tab Chlorthalidone", dose="12.5 mg", route="PO", frequency="1-0-0", duration="Continue"),
            ],
        ),
    ),
    # --- Viral fever
    dict(
        patient=dict(name="Meena Kharat", sex="F", dob="1995-09-03", phone="9822011017"),
        record=dict(
            age_at_admission="30 y", ward_bed="GW/10",
            admission_date="2026-07-08T14:00:00", discharge_date="2026-07-10T10:00:00",
            diagnosis="Acute viral fever",
            presenting_complaints="Fever 3 days with body ache and sore throat, no rash",
            history="Family members with similar symptoms",
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
        patient=dict(name="Yamuna Waghmare", sex="F", dob="1976-02-26", phone="9822011018"),
        record=dict(
            age_at_admission="50 y", ward_bed="GW/11",
            admission_date="2026-05-27T10:00:00", discharge_date="2026-05-30T11:00:00",
            diagnosis="Severe iron deficiency anemia",
            presenting_complaints="Progressive weakness, breathlessness on exertion, pale appearance",
            history="Heavy menstrual bleeding several months",
            temperature="98.4 F", pulse="104/min", bp="102/64", spo2="98%",
            investigations="Hb 6.2, microcytic hypochromic picture, ferritin low",
            course_in_hospital="One PCV transfusion, IV iron started, gynae opinion for menorrhagia",
            advice="Iron rich diet, continue iron tablets 3 months, gynaecology follow-up",
            treatment_items=[
                dict(category="hospital", drug="Inj Iron Sucrose", dose="200 mg", route="IV", frequency="Alternate days", duration="3 doses"),
                dict(category="discharge", drug="Tab Ferrous Ascorbate-Folic Acid", dose="100/1.5 mg", route="PO", frequency="1-0-1", duration="3 months", instructions="Avoid with tea or milk"),
            ],
        ),
    ),
]


def seed() -> None:
    with TestClient(app) as client:
        existing = client.get("/api/patients", params={"q": CASES[0]["patient"]["phone"]}).json()
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
            payload["doctor_name"] = payload.get("doctor_name", "Dr. R. Shah")
            rresp = client.post("/api/records", json=payload)
            rresp.raise_for_status()
            print(f"Seeded record {rresp.json()['id']}: {patient['name']} - {payload['diagnosis']}")
        print(f"\nDone: {len(CASES)} records seeded.")


if __name__ == "__main__":
    seed()
