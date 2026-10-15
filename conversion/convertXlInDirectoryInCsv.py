
import os
import pandas as pd


def convert_excel_to_csv(directory):
    # Assurez-vous que le répertoire existe
    if not os.path.isdir(directory):
        print(f"Le répertoire {directory} n'existe pas.")
        return

    # Crée un sous-dossier pour les fichiers CSV
    output_dir = os.path.join(directory, "csv_output")
    os.makedirs(output_dir, exist_ok=True)

    # Parcourir tous les fichiers du répertoire
    for filename in os.listdir(directory):
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            file_path = os.path.join(directory, filename)
            try:
                print(file_path)
                # Lire l'onglet "Bénéficiaires"
                xlsx = pd.ExcelFile(file_path)
                print(1)
                print(xlsx.sheet_names)
                df = pd.read_excel(xlsx, sheet_name=xlsx.sheet_names[0])
                
                # Définir le nom de fichier CSV
                csv_filename = f"{os.path.splitext(filename)[0]}.csv"
                csv_path = os.path.join(output_dir, csv_filename)
                
                # Enregistrer au format CSV
                df.to_csv(csv_path, index=False, encoding='utf-8')
                print(f"Converti : {filename} → {csv_filename}")
            except Exception as e:
                print(f"Erreur lors de la conversion de {filename} : {e}")


# Exemple d'utilisation
directory_path = "C:/ONE DRIVE/OneDrive - Publicis Groupe/privée/CSE/liste BDD utilisateur/"
# convert_excel_to_csv(directory_path)


