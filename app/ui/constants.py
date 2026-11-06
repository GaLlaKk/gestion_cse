from services.paths import project_root

ROOT_DIRECTORY = project_root()
SWILE_DIRECTORY = ROOT_DIRECTORY / "swile_active_directory"
INPUT_DIRECTORY = SWILE_DIRECTORY / "in"
OUTPUT_DIRECTORY = SWILE_DIRECTORY / "out"
ACTIVE_DIRECTORY_OUTPUT = ROOT_DIRECTORY / "liste_salarie_active_directory" / "out"
ACTIVE_DIRECTORY_INPUT = ROOT_DIRECTORY / "liste_salarie_active_directory" / "in"
REQUIRED_COLUMNS = {
    "swile": {"Prénom", "Nom", "Email", "Matricule"},
    "active_directory": {"Nom", "Email", "Identifiant", "Poste"},
    "active_directory_previous": {"Nom", "Email", "Identifiant", "Poste"},
    "template": {"Prénom", "Nom", "Email", "Matricule"},
}
TITLES = {
    "swile": "FICHIER SWILE - Liste actuelle des salariés",
    "active_directory": "FICHIER ACTIVE DIRECTORY - Export des salariés",
    "active_directory_previous": "FICHIER ACTIVE DIRECTORY PRECEDENT (optionnel)",
    "template": "MODELE SWILE - CSV d'import",
}
INSTRUCTIONS = {
    "swile": "CSV SWILE ATTENDU ici (séparateur « ; »).",
    "active_directory": "CSV ACTIVE DIRECTORY ATTENDU ici (séparateur « , »).",
    "active_directory_previous": (
        "CSV ACTIVE DIRECTORY PRECEDENT (optionnel) pour compléter "
        "les comptes manquants s’ils sont toujours visibles."
    ),
    "template": "MODELE SWILE ATTENDU ici (séparateur « ; »).",
}
INPUT_HIGHLIGHTS = {
    "swile": ("SWILE", "#0a4f8a"),
    "active_directory": ("ACTIVE DIRECTORY", "#176b35"),
    "active_directory_previous": ("ACTIVE DIRECTORY PRECEDENT", "#0f5b7a"),
    "template": ("MODELE SWILE", "#176b35"),
}
DELIMITERS = {
    "swile": ";",
    "active_directory": ",",
    "active_directory_previous": ",",
    "template": ";",
}
DEFAULT_TEMPLATE_FILE = (
    "collaborators_template_090d2568-c182-4cf4-8b3a-81fefee3a297.csv"
)
ACTIVE_DIRECTORY_CONFIG_FIELDS = (
    ("start_user_email", "Adresse de départ"),
    ("client_id", "Identifiant de l’application"),
    ("authority", "Autorité Microsoft"),
    ("report_domain", "Domaine de rapport"),
)
