
from pypdf import PdfWriter
import os

# Initialiser le merger
merger = PdfWriter()
path='C:\\ONE DRIVE\\OneDrive - Publicis Groupe\\Documents\\20240124 Jugement JAF garde Laura Vincent\\'
# Ajouter les fichiers

merger.append(os.path.join(path, '2026-04-16_1_Secure_Scan.pdf'))
merger.append(os.path.join(path, '2026-04-16_2_Secure_Scan.pdf'))
merger.append(os.path.join(path, '2026-04-16_3_Secure_Scan.pdf'))
merger.append(os.path.join(path, '2026-04-16_4_Secure_Scan.pdf'))
merger.append(os.path.join(path, '2026-04-16_5_Secure_Scan.pdf'))
merger.append(os.path.join(path, '2026-04-16_6_Secure_Scan.pdf'))
merger.append(os.path.join(path, '2026-04-16_7_Secure_Scan.pdf'))



# Sauvegarder le résultat
merger.write(os.path.join(path, '2026-04-16_Secure_Scan.pdf'))
merger.close()

