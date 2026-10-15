from pptx import Presentation   #pip install python-pptx
from PIL import Image           #pip install pillow

# Ouvrir la présentation
# prs = Presentation("C:\ONE DRIVE\OneDrive - Publicis Groupe\Bureau\CSE EPSILON France 012025 DIF local.pptx")
prs = Presentation("C:/CSE EPSILON France 042025.pptx")

# Boucle à travers les slides
for i, slide in enumerate(prs.slides):
    # Enregistrer chaque slide en image
    slide.shapes[0].image.save(f"slide_{i + 1}.png")

print("Extraction terminée !")
