import os
import re
from datetime import datetime
import pandas as pd

# Chemin du répertoire contenant les fichiers CSV
repertoire = "C:/ONE DRIVE/OneDrive - Publicis Groupe/privée/CSE/liste BDD utilisateur/csv_output/"

# Expression régulière pour capturer la date dans le nom du fichier
pattern = r"export_beneficiaires_\d+_(\d{4}-\d{2}-\d{2})\.csv"

# Fonction pour calculer l'âge
def calculer_age(date_naissance, date_reference):
    # print(date_naissance)
    if(not isinstance(date_naissance,datetime) or not isinstance(date_reference,datetime)):
        return None
    return date_reference.year - date_naissance.year - ((date_reference.month, date_reference.day) < (date_naissance.month, date_naissance.day))

# Fonction pour calculer l'ancienneté
def calculer_anciennete(date_arrivee, date_reference):
    if(not isinstance(date_arrivee,datetime) or not isinstance(date_reference,datetime)):
        return None
    return date_reference.year - date_arrivee.year - ((date_reference.month, date_reference.day) < (date_arrivee.month, date_arrivee.day))

# Fonction pour regrouper par tranches
def categoriser_tranche(valeur, tranches):
    if(valeur):
        for limite_min, limite_max, label in tranches:
            if limite_min <= valeur <= limite_max:
                return label
    return "Non défini"

# Définition des tranches d'âge et d'ancienneté
tranches_age = [(0, 24, "0-24 ans"), (25, 34, "25-34 ans"), (35, 44, "35-44 ans"), (45, 54, "45-54 ans"), (55, 64, "55-64 ans"), (65, 200, "65 ans et plus"),(-1,-1,"Non défini")]
tranches_anciennete = [(0, 1, "0-1 an"), (2, 5, "2-5 ans"), (6, 10, "6-10 ans"), (11, 20, "11-20 ans"), (21, 100, "21 ans et plus"),(-1,-1,"Non défini")]

# Liste pour stocker les fichiers avec leur date
fichiers_dates = []

# Parcourir les fichiers du répertoire
for fichier in os.listdir(repertoire):
    match = re.search(pattern, fichier)
    if match:
        date_str = match.group(1)
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        fichiers_dates.append((fichier, date_obj))

# Trier les fichiers par date décroissante
fichiers_dates.sort(key=lambda x: x[1], reverse=True)

if fichiers_dates:
    # Fichier de référence le plus récent
    fichier_reference, date_reference = fichiers_dates[0]

    # Charger le fichier de référence avec pandas
    df_reference = pd.read_csv(os.path.join(repertoire, fichier_reference))#, parse_dates=["Date de naissance (JJ/MM/AAAA)", "Date d'entrée dans l'entreprise (JJ/MM/AAAA)"])
    df_reference.insert(0,"ID",df_reference['Identifiant\n(obligatoire - peut être identique à l’adresse email)'])

    df_reference["Date de naissance (JJ/MM/AAAA)"] = pd.to_datetime(df_reference["Date de naissance (JJ/MM/AAAA)"], format='%d/%m/%Y')
    df_reference["Date d'entrée dans l'entreprise (JJ/MM/AAAA)"] = pd.to_datetime(df_reference["Date d'entrée dans l'entreprise (JJ/MM/AAAA)"], format='%d/%m/%Y')
    
    df_reference = df_reference[["ID","Site de rattachement","Date de naissance (JJ/MM/AAAA)","Date d'entrée dans l'entreprise (JJ/MM/AAAA)"]]

    # print(df_reference)
    for fichier_current, date_current in fichiers_dates:  # looping through row
        # print(fichier_current)
        df_current = pd.read_csv(os.path.join(repertoire, fichier_current))#, parse_dates=["Date de naissance (JJ/MM/AAAA)", "Date d'entrée dans l'entreprise (JJ/MM/AAAA)"])
        # print(1)

        df_current.insert(0,"ID",df_current['Identifiant\n(obligatoire - peut être identique à l’adresse email)'])

        df_current = df_current[["ID","Actif (Actif/Inactif) (obligatoire)"]]
        # print(2)

        df_current[date_current.date()] = df_current["Actif (Actif/Inactif) (obligatoire)"]
        # print(2)
        
        # print(3)
        df_current = df_current[["ID",date_current.date()]]
        # print(df_current)
        # print(4)
        df_reference = pd.concat([df_reference, df_current], axis=1)
        # print(5)
        # comment: 
    # end for
    # df_reference.to_csv(os.path.join(repertoire, f"test_{date_reference.date()}.csv"), index=False)

    # print(df_reference)
    # print(6)
    
    # Calculer l'âge et l'ancienneté
    
    sites = ["Paris", "Lille"]
    # Extraction des labels
    labels = [t[2] for t in tranches_anciennete]
    resultatAncienneteGlobal = pd.DataFrame([(site, label) for site in sites for label in labels], columns=["Site de rattachement", "tranche_anciennete"])

    labels = [t[2] for t in tranches_age]
    resultatAgeGlobal = pd.DataFrame([(site, label) for site in sites for label in labels], columns=["Site de rattachement", "tranche_age"])

    fichiers_dates.sort(key=lambda x: x[1], reverse=False)
    print(df_reference)
    for fichier_current, date_current in fichiers_dates:  # looping through row
        print(fichier_current)
        df_perimetre = df_reference.where(df_reference[date_current.date()]=="Actif")
        
        # df_perimetre.to_csv(os.path.join(repertoire, f"df_perimetre_{date_current.date()}.csv"), index=False,sep=";")
        df_perimetre["âge"] = df_perimetre["Date de naissance (JJ/MM/AAAA)"].apply(lambda x: calculer_age(x, date_current))
        df_perimetre["ancienneté"] = df_perimetre["Date d'entrée dans l'entreprise (JJ/MM/AAAA)"].apply(lambda x: calculer_anciennete(x, date_current))
        df_perimetre["tranche_age"] = df_perimetre["âge"].apply(lambda x: categoriser_tranche(x, tranches_age))
        df_perimetre["tranche_anciennete"] = df_perimetre["ancienneté"].apply(lambda x: categoriser_tranche(x, tranches_anciennete))
        # print(df_perimetre)
        resultatAnciennete = df_perimetre.groupby(["Site de rattachement", "tranche_anciennete"]).size().reset_index(name=date_current.date())
        resultatAge = df_perimetre.groupby(["Site de rattachement", "tranche_age"]).size().reset_index(name=date_current.date())
        # print(resultatAnciennete)
        # print(resultatAge)
        # if(resultatAncienneteGlobal is None):
        #     resultatAncienneteGlobal = resultatAnciennete
        #     resultatAgeGlobal = resultatAge
        # else:
        resultatAncienneteGlobal = pd.concat([resultatAncienneteGlobal, resultatAnciennete[date_current.date()]], axis=1)
        resultatAgeGlobal = pd.concat([resultatAgeGlobal, resultatAge[date_current.date()]], axis=1)
        print(date_current.date())
        print(resultatAgeGlobal)
   # print(resultatAncienneteGlobal)
    # print(resultatAgeGlobal)
    resultatAncienneteGlobal.to_csv(os.path.join(repertoire, f"volumetrieAnciennete_{date_reference.date()}.csv"), index=False,sep=";")
    resultatAgeGlobal.to_csv(os.path.join(repertoire, f"volumetrieAge_{date_reference.date()}.csv"), index=False,sep=";")

    # resultatAnciennete.insert(0,"date_reference",date_reference.date())
    # resultatAge.insert(0,"date_reference",date_reference.date())
    # Afficher le résultat
    

    # Optionnel : Sauvegarder en CSV pour analyser plus tard
    # resultat.to_csv(os.path.join(repertoire, f"volumetrie_{date_reference.date()}.csv"), index=False)

else:
    print("Aucun fichier correspondant trouvé.")
