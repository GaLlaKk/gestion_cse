import xml.etree.ElementTree as ET
import pandas as pd
import re
from datetime import datetime

# 📌 Fichiers sources
csv_file = "C:/Users/gaechene/Downloads/export_beneficiaires_1056691_2025-02-24.csv"

# 🔹 Charger le fichier CSV des bénéficiaires
df_benef = pd.read_csv(csv_file, sep=";", encoding="utf-8")

# Création d'un dictionnaire {Nom Prénom : {IBAN, BIC, RUM}}
beneficiaires = {
    f"{row['Prénom (obligatoire)']} {row['Nom (obligatoire)']}": {
        "IBAN": row["IBAN"],
        "BIC": row["BIC"],
        "RUM": row["Référence Unique de Mandat (RUM)"]
    }
    for _, row in df_benef.iterrows()
}

# 🔹 Données source texte
past = """Gestion - Trésorerie Bénéficiaire
Remise En Banque "N° R_S_20250217"
Banque BNP PARIBAS EPSILON FRANCE ASC
Iban FR76 3000 4003 7000 0102 7550 424
Adresse 2 Bd Beaumarchais
Code postal & Ville 75011 Paris
N° de bordereau Date de remise en banque Nombre de paiement(s) Montant total
R_S_20250217 17/02/2025 46 2022 €
Paiement(s)
# Montant Émetteur Règlement Banque Date de règlement N° chèque /
Rum
Inscription
3368 60 € Rayan BAHMED Virement émis - 17/02/2025 - 5416
3369 55.03 € Constance Mabesoone Virement émis - 17/02/2025 - 5417
3370 50 € Constance Mabesoone Virement émis - 17/02/2025 - 5418
3371 50 € Leo Belorgey Virement émis - 17/02/2025 - 5421
3372 60 € ALLISON SAINT-MICHEL Virement émis - 17/02/2025 - 5424
3373 40 € ALLISON SAINT-MICHEL Virement émis - 17/02/2025 - 5425
3374 40 € William Baudin Virement émis - 17/02/2025 - 5426
3375 50 € William Baudin Virement émis - 17/02/2025 - 5428
3376 50 € Julien Mallet Virement émis - 17/02/2025 - 5429
3377 40 € Ronan Bourgeois Virement émis - 17/02/2025 - 5431
3378 60 € Ronan Bourgeois Virement émis - 17/02/2025 - 5432
3379 60 € Franck Yvan Kouemou Ngankam Virement émis - 17/02/2025 - 5433
3380 60 € Julien Mallet Virement émis - 17/02/2025 - 5436
3381 40 € Julien Mallet Virement émis - 17/02/2025 - 5437
3382 39.99 € ahmad Masri Virement émis - 17/02/2025 - 5438
3383 50 € Franck Yvan Kouemou Ngankam Virement émis - 17/02/2025 - 5435
3384 39 € CLAIRE BERGAMINI Virement émis - 17/02/2025 - 5439
3385 40 € achraf afillou Virement émis - 17/02/2025 - 5440
3386 39 € sherley horace Virement émis - 17/02/2025 - 5441
3387 40 € Iris Routier Virement émis - 17/02/2025 - 5443
3388 39 € Iris Routier Virement émis - 17/02/2025 - 5444
3389 50 € Lionelle LE GALL Virement émis - 17/02/2025 - 5445
3390 40 € Lionelle LE GALL Virement émis - 17/02/2025 - 5446
3391 50 € David Sénécaut Virement émis - 17/02/2025 - 5449
3392 30 € Florent Atakora Virement émis - 17/02/2025 - 5450
3393 10 € Florent Atakora Virement émis - 17/02/2025 - 5451
3394 39.99 € Heloise Dumortier Virement émis - 17/02/2025 - 5452
3395 40 € Franck Yvan Kouemou Ngankam Virement émis - 17/02/2025 - 5434
3396 40 € Emilie Degodet Virement émis - 17/02/2025 - 5453
3397 30 € Eliano Carlone Virement émis - 17/02/2025 - 5454
3398 40 € Hébert Nguyen Virement émis - 17/02/2025 - 5455
3399 50 € Hébert Nguyen Virement émis - 17/02/2025 - 5456
3400 50 € Pauline Lephay Virement émis - 17/02/2025 - 5457
3401 40 € Jacques Zhang Virement émis - 17/02/2025 - 5458
3402 40 € Nathalie Leurent Virement émis - 17/02/2025 - 5459
3403 60 € Thomas Laillet Virement émis - 17/02/2025 - 5460
3404 40 € nathalie west Virement émis - 17/02/2025 - 5461
3405 50 € nathalie west Virement émis - 17/02/2025 - 5462
3406 60 € nathalie west Virement émis - 17/02/2025 - 5463
3407 40 € Eva Schmitthenner Virement émis - 17/02/2025 - 5465
3408 50 € Priscilla Linxe Virement émis - 17/02/2025 - 5470
3409 10 € Eliano Carlone Virement émis - 17/02/2025 - 5471
3410 40 € Cecile Schaub Virement émis - 17/02/2025 - 5472
3411 50 € Anne Dufour Virement émis - 17/02/2025 - 5473
3412 19.99 € Jordy Djiogo Virement émis - 17/02/2025 - 5475
3413 50 € Jordy Djiogo Virement émis - 17/02/2025 - 5476
# Montant Émetteur Règlement Banque Date de règlement N° chèque /
Rum
Inscription"""

# 🔹 Extraction de la date du bordereau
match = re.search(r"R_S_\d+\s+(\d{2}/\d{2}/\d{4})", past)
if match:
    raw_date = match.group(1)
    date_obj = datetime.strptime(raw_date, "%d/%m/%Y")
    iso_date = date_obj.strftime("%Y-%m-%d")
    iso_datetime = date_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
else:
    raise ValueError("Date non trouvée dans le texte source.")

# 🔹 Extraction des paiements
lines = past.split("\n")
transactions = []
for line in lines:
    parts = line.split(" Virement émis - ")
    if len(parts) == 2:
        details = parts[1].split(" - ")
        if len(details) == 2:
            num, montant, emetteur = parts[0].split(" ", 2)
            transactions.append({
                "EndToEndId": num,
                "Montant": montant.replace("€", "").strip(),
                "Emetteur": emetteur.strip().replace("€ ", ""),
                "Date": details[0].strip(),
                "Rum": details[1].strip()
            })

# 🔹 Création de l'élément racine XML
root = ET.Element("Document", xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03")

# 📌 En-tête SEPA
cstmrCdtTrfInitn = ET.SubElement(root, "CstmrCdtTrfInitn")
grpHdr = ET.SubElement(cstmrCdtTrfInitn, "GrpHdr")
ET.SubElement(grpHdr, "MsgId").text = f"{iso_date.replace('-', '')}/1056691/001"
ET.SubElement(grpHdr, "CreDtTm").text = iso_datetime
ET.SubElement(grpHdr, "NbOfTxs").text = str(len(transactions))
ET.SubElement(grpHdr, "CtrlSum").text = str(sum(float(t["Montant"]) for t in transactions))
InitgPty = ET.SubElement(grpHdr, "InitgPty")
ET.SubElement(InitgPty, "Nm").text = "CSE EPSILON FRANCE"

# 📌 Paiements
pmtInf = ET.SubElement(cstmrCdtTrfInitn, "PmtInf")
ET.SubElement(pmtInf, "PmtInfId").text = f"R_S_{iso_date.replace('-', '')}"
ET.SubElement(pmtInf, "PmtMtd").text = "TRF"
ET.SubElement(pmtInf, "NbOfTxs").text = str(len(transactions))
ET.SubElement(pmtInf, "CtrlSum").text = str(sum(float(t["Montant"]) for t in transactions))

# Type de paiement SEPA
pmtTpInf = ET.SubElement(pmtInf, "PmtTpInf")
svcLvl = ET.SubElement(pmtTpInf, "SvcLvl")
ET.SubElement(svcLvl, "Cd").text = "SEPA"

ET.SubElement(pmtInf, "ReqdExctnDt").text = iso_date

# 🔹 Fixation des valeurs en dur
dbtr = ET.SubElement(pmtInf, "Dbtr")
ET.SubElement(dbtr, "Nm").text = "CSE EPSILON FRANCE"

dbtrAcct = ET.SubElement(pmtInf, "DbtrAcct")
id_tag = ET.SubElement(dbtrAcct, "Id")
ET.SubElement(id_tag, "IBAN").text = "FR7630004003700001027550424"
ET.SubElement(dbtrAcct, "Ccy").text = "EUR"

dbtrAgt = ET.SubElement(pmtInf, "DbtrAgt")
finInstnId = ET.SubElement(dbtrAgt, "FinInstnId")
ET.SubElement(finInstnId, "BIC").text = "BNPAFRPPXXX"


# 📌 Ajout des transactions avec IBAN/BIC/RUM
for t in transactions:
    emetteur_nom = t["Emetteur"]

    # Vérifier si l'émetteur a un IBAN
    if emetteur_nom in beneficiaires:
        iban = beneficiaires[emetteur_nom]["IBAN"]
        bic = beneficiaires[emetteur_nom]["BIC"]
        rum = beneficiaires[emetteur_nom]["RUM"]
    else:
        raise ValueError(f"🚨 ERREUR : Aucun RIB trouvé pour {emetteur_nom}. Vérifiez le fichier CSV.")

    cdtTrfTxInf = ET.SubElement(pmtInf, "CdtTrfTxInf")
    pmtId = ET.SubElement(cdtTrfTxInf, "PmtId")
    ET.SubElement(pmtId, "EndToEndId").text = t["EndToEndId"]

    amt = ET.SubElement(cdtTrfTxInf, "Amt")
    ET.SubElement(amt, "InstdAmt", Ccy="EUR").text = t["Montant"]

    cdtrAgt = ET.SubElement(cdtTrfTxInf, "CdtrAgt")
    finInstnId = ET.SubElement(cdtrAgt, "FinInstnId")
    ET.SubElement(finInstnId, "BIC").text = bic

    cdtr = ET.SubElement(cdtTrfTxInf, "Cdtr")
    ET.SubElement(cdtr, "Nm").text = emetteur_nom

    cdtrAcct = ET.SubElement(cdtTrfTxInf, "CdtrAcct")
    id_tag = ET.SubElement(cdtrAcct, "Id")
    ET.SubElement(id_tag, "IBAN").text = iban

    rmtInf = ET.SubElement(cdtTrfTxInf, "RmtInf")
    ET.SubElement(rmtInf, "Ustrd").text = f"Paiement ref : {t['EndToEndId']}"

# 🔹 Sauvegarde du fichier XML
filename = f"bordereau_SEPA_{iso_date.replace('-', '')}.xml"
tree = ET.ElementTree(root)
tree.write(filename, encoding="utf-8", xml_declaration=True)

print(f"✅ Bordereau SEPA généré avec succès : {filename}")
