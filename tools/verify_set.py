"""Verify every anchor judgement and every provision for the expanded golden set.

Nothing is encoded that does not pass here. Two checks:
  1. Anchor: case_id resolves, and has paragraphs classified ratio/reasoning/order,
     because only those are attributable to the court.
  2. Provision: readable back verbatim from some store, with the store named.
"""
import json
import sqlite3

CHUNKS = "legal_database/vector_store/chunks.db"
ATTRIBUTABLE = ("ratio", "reasoning", "order")

ANCHORS = [
    "HC_1986_SHEIK_KHASIM_BI_VS_THE_STATE",
    "HC_1992_KURRA_DASARATHA_RAMAIAH_AND_ORS_VS_STATE_OF_ANDHRA_PRADESH",
    "HC_2004_GIRISH_SARWATE_VS_STATE_OF_AP_REPRESENTED_BY_PUBLIC",
    "HC_1998_PAVAN_KUMAR_AND_ANR_VS_K_GOPALAKRISHNA_AND_ANR",
    "HC_2006_ADAPA_TATARAO_VS_CHAMANTULA_MAHALAKSHMI",
    "HC_2000_SOHAM_MODI_AND_ANOTHER_VS_SPECIAL_COURT_UNDER_AP_LAND_GRABBING",
    "HC_2000_DADI_REDDY_SIVANARAYANA_REDDY_VS_KASI_REDDY_CHINNAMMA",
    "HC_1998_SARDAR_AMARJEET_SINGH_VS_NANDU_BAI_AND_ORS",
    "HC_2002_RANGA_REDDY_VS_SADHU_PADAMMA_AND_ORS",
    "HC_1981_T_BHASKAR_RAO_VS_T_GABRIEL_AND_ORS",
    "HC_1992_RASALA_SURYA_PRAKASARAO_AND_OTHERS_VS_RASALA_VENKATESWARARAO_AND_OTHERS",
    "HC_1996_SMT_K_RACHAMMA_VS_SMT_BIMAL_BAI_AND_ANR",
    "HC_2005_GORANTLA_VENKATESWARA_RAO_VS_KOLLA_VEERA_RAGHAVA_RAO_AND_ANR",
    "HC_2003_A_YESUBABU_VS_D_APPALA_SWAMY_AND_ANR",
    "HC_1955_THAVVA_SUBRAHMANYAM_VS_CHENNA_VENKATARATNAM",
    "HC_1990_USMAN_KHAN_BAHAMANI_VS_FATHIMUNNISA_BEGUM_AND_OTHERS",
    "HC_1990_ALL_INDIA_MUSLIM_ADVOCATES_FORUM_VS_OSMAN_KHAN_BRAHAMAINI_BASHA_AND_ORS",
    "HC_1999_G_PADMINI_VS_G_SIVANANDA_BABU",
    "HC_1980_L_CHANDRAN_VS_VENKATALAKSHMI_AND_ANR",
    "HC_2007_MOHAMMEDIA_CO-OPERATIVE_BUILDING_VS_LAKSHMI_SREENIVASA_CO-OPERATIVE",
    "HC_1993_EMPLOYEES_ASSOCIATION_REP_BY_ITS_VS_SRI_CHENNA_KESHAVA_SWAMY_TEMPLE_REP_BY",
    "HC_1968_KESIREDDY_APPALA_SWAMY_AND_ORS_VS_SPECIAL_TAHSILDAR_LAND_ACQUISITION",
    "HC_1989_R_SREENIVASA_RAO_VS_LABOUR_COURT_HYDERABAD_AND_ANR",
    "HC_1994_GADDIPATI_SAMBRAJYAM_AND_ANR_VS_PANGULURI_MAHALAKSHMAMMA_AND_ORS",
    "HC_1999_N_MOHANA_KUMAR_VS_BAYANI_LAKSHMI_NARASIMHAIAH_AND_OTHERS",
    "HC_2001_OPTS_MARKETING_P_LTD_AND_OTHERS_VS_STATE_OF_AP_AND_ANOTHER",
    "HC_2001_GENERAL_MANAGER_SC_RAILWAY_SECBAD_VS_SRI_RAMA_ENGINEERING_CONSTRUCTIONS_AND",
    "HC_1999_REFERRING_OFFICER_REP_BY_STATE_OF_AP_VS_SHEKAR_NAIR_GURU_AND_ORS",
    "HC_1987_BHAGWANDAS_VS_MOHD_ARIF",
    "HC_2004_EUREKA_ESTATES_P_LTD_VS_AP_STATE_CONSUMER_DISPUTES_REDRESSAL",
    "HC_2007_BRANCH_MANAGER_UNITED_INDIA_INSURANCE_VS_MYAKALA_SULOCHANA_AND_ORS",
]

# (label, act_id LIKE pattern, section_number)
PROVISIONS = [
    ("CrPC 1973 s.57 - 24hr production", "%the_code_of_criminal_procedure_1973%", "57"),
    ("CrPC 1973 s.167 - remand", "%the_code_of_criminal_procedure_1973%", "167"),
    ("CrPC 1973 s.438 - anticipatory bail", "%the_code_of_criminal_procedure_1973%", "438"),
    ("CrPC 1973 s.439 - bail", "%the_code_of_criminal_procedure_1973%", "439"),
    ("CrPC 1973 s.482 - inherent power", "%the_code_of_criminal_procedure_1973%", "482"),
    ("BNSS 2023 s.58", "%BHARATIYA NAGARIK SURAKSHA SANHITA%", "58"),
    ("BNSS 2023 s.187 - remand", "%BHARATIYA NAGARIK SURAKSHA SANHITA%", "187"),
    ("BNSS 2023 s.482 - anticipatory bail", "%BHARATIYA NAGARIK SURAKSHA SANHITA%", "482"),
    ("BNSS 2023 s.528 - inherent power", "%BHARATIYA NAGARIK SURAKSHA SANHITA%", "528"),
    ("IPC 1860 s.415 - cheating", "%the_indian_penal_code_1860%", "415"),
    ("IPC 1860 s.420", "%the_indian_penal_code_1860%", "420"),
    ("IPC 1860 s.447 - criminal trespass", "%the_indian_penal_code_1860%", "447"),
    ("BNS 2023 s.318 - cheating", "%bharatiya_nyaya_sanhita_2023%", "318"),
    ("BNS 2023 s.329 - criminal trespass", "%bharatiya_nyaya_sanhita_2023%", "329"),
    ("Specific Relief Act s.6", "%SPECIFIC RELIEF%", "6"),
    ("Specific Relief Act s.16 - readiness", "%SPECIFIC RELIEF%", "16"),
    ("Specific Relief Act s.20 - discretion", "%SPECIFIC RELIEF%", "20"),
    ("Limitation Act s.18 - acknowledgment", "%the_limitation_act_1963%", "18"),
    ("Limitation Act s.19 - part payment", "%the_limitation_act_1963%", "19"),
    ("Limitation Act s.14 - exclusion", "%the_limitation_act_1963%", "14"),
    ("Limitation Act Article 65", "%the_limitation_act_1963%", "Article_65"),
    ("Limitation Act Article 54 - sp perf", "%the_limitation_act_1963%", "Article_54"),
    ("Limitation Act Article 113", "%the_limitation_act_1963%", "Article_113"),
    ("Registration Act s.17 - compulsory", "%the_registration_act_1908%", "17"),
    ("Registration Act s.49 - effect", "%the_registration_act_1908%", "49"),
    ("Evidence Act s.65 - secondary", "%the_indian_evidence_act_1872%", "65"),
    ("Evidence Act s.66 - notice", "%the_indian_evidence_act_1872%", "66"),
    ("NI Act s.138", "%the_negotiable_instruments_act_1881%", "138"),
    ("NI Act s.139 - presumption", "%the_negotiable_instruments_act_1881%", "139"),
    ("NI Act s.142 - cognizance", "%the_negotiable_instruments_act_1881%", "142"),
    ("CPC 1908 s.9 - jurisdiction", "%the_code_of_civil_procedure_1908%", "9"),
    ("CPC 1908 s.80 - notice to govt", "%the_code_of_civil_procedure_1908%", "80"),
    ("Muslim Women 1986 s.3", "%MUSLIM WOMEN (PROTECTION OF RIGHTS ON DIVOR%", "3"),
    ("Muslim Women 1986 s.4", "%MUSLIM WOMEN (PROTECTION OF RIGHTS ON DIVOR%", "4"),
    ("Hindu Marriage Act s.13", "%the_hindu_marriage_act_1955%", "13"),
    ("Guardians and Wards Act s.17", "%the_guardians_and_wards_act_1890%", "17"),
    ("Guardians and Wards Act s.25", "%the_guardians_and_wards_act_1890%", "25"),
    ("Wakf Act 1995 s.51", "%WAKF ACT, 1995%", "51"),
    ("Transfer of Property Act s.53A", "%the_transfer_of_property_act_1882%", "53A"),
    ("Indian Easements Act s.15", "%the_indian_easements_act_1882%", "15"),
    ("Domestic Violence Act 2005 s.17", "%domestic_violence_act_2005%", "17"),
    ("Domestic Violence Act 2005 s.19", "%domestic_violence_act_2005%", "19"),
]

con = sqlite3.connect(f"file:{CHUNKS}?mode=ro", uri=True)

print("=" * 96)
print("ANCHOR JUDGEMENTS")
print("=" * 96)
ok_a, bad_a = 0, []
for cid in ANCHORS:
    rows = con.execute("select atom_type, count(*) from chunks where case_id=? group by atom_type",
                       (cid,)).fetchall()
    total = sum(n for _, n in rows)
    attr = sum(n for t, n in rows if t in ATTRIBUTABLE)
    if total == 0:
        print(f"  MISSING            {cid}")
        bad_a.append(cid)
        continue
    head = json.loads(con.execute("select blob from chunks where case_id=? limit 1", (cid,)).fetchone()[0])
    flag = "OK  " if attr >= 5 else "THIN"
    if attr < 5:
        bad_a.append(cid)
    else:
        ok_a += 1
    print(f"  {flag}  attr={attr:3d}/{total:3d} ({attr/total:3.0%})  {head.get('year')}  cited_by={head.get('cited_by_count'):>3}  {cid[:70]}")

print()
print("=" * 96)
print("PROVISIONS")
print("=" * 96)
ok_p, bad_p = 0, []
for label, like, sec in PROVISIONS:
    r = con.execute("""select act_id, atom_type from chunks
                       where doc_type='bare_act' and act_id like ? and section_number=? limit 1""",
                    (like, sec)).fetchone()
    if r:
        ok_p += 1
        print(f"  HELD      {label:42s} <- {r[0][:58]}")
    else:
        bad_p.append(label)
        print(f"  NOT HELD  {label:42s} <- (no store)")

print()
print(f"anchors OK {ok_a}/{len(ANCHORS)}   provisions HELD {ok_p}/{len(PROVISIONS)}")
if bad_a:
    print("ANCHORS TO DROP:", bad_a)
if bad_p:
    print("PROVISIONS TO DROP:", bad_p)
con.close()
