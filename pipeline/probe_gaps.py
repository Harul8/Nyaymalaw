"""Check identifier and section-number variants before reporting any Act as absent.

This is the union-across-stores rule applied to my own verification pass: a
single lookup establishes nothing about the corpus, only about the query.
"""
import sqlite3

con = sqlite3.connect("file:legal_database/vector_store/chunks.db?mode=ro", uri=True)

Q_ACTS = """select act_id, count(*) as n, count(distinct section_number) as nsec
            from chunks where doc_type='bare_act' and act_id like ?
            group by act_id order by nsec desc limit 8"""

Q_SEC = """select act_id, atom_type from chunks
           where doc_type='bare_act' and act_id like ? and section_number=? limit 1"""


def acts(label, like):
    print(f"\n[{label}] act_ids LIKE {like}")
    rows = con.execute(Q_ACTS, (like,)).fetchall()
    if not rows:
        print("   -- none --")
    for a, n, nsec in rows:
        print(f"   secs={nsec:>4} chunks={n:>5}  {a[:72]}")


def secs(like, pats):
    for pat in pats:
        r = con.execute(Q_SEC, (like, pat)).fetchone()
        print(f"     s.{pat:<9} -> {('HELD  ' + r[0][:52]) if r else 'not found'}")


def listsec(act_id, limit=48):
    r = [x[0] for x in con.execute(
        "select distinct section_number from chunks where act_id=? and section_number is not null",
        (act_id,))]

    def key(v):
        import re
        m = re.match(r"^(\d+)", str(v))
        return (int(m.group(1)) if m else 99999, str(v))
    r = sorted(r, key=key)
    print(f"   {act_id[:60]}  ({len(r)} sections)")
    print("     ", r[:limit])


acts("Hindu Marriage", "%hindu_marriage%")
acts("Hindu Marriage UPPER", "%HINDU MARRIAGE%")
print("   probing section variants on the snake_case id:")
secs("%the_hindu_marriage_act_1955%", ["13", "13(1)", "13A", "13-A", "12", "9", "23"])
listsec("the_hindu_marriage_act_1955")

acts("Transfer of Property", "%transfer_of_property%")
acts("Transfer of Property UPPER", "%TRANSFER OF PROPERTY%")
secs("%the_transfer_of_property_act_1882%", ["53A", "53-A", "53", "54", "55", "58"])

acts("Domestic Violence", "%domestic_violence%")
acts("Domestic Violence UPPER", "%DOMESTIC VIOLENCE%")
secs("%protection_of_women_from_domestic_violence_act_2005%", ["17", "19", "12", "18", "20"])

con.close()
