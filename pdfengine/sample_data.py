"""
Dataset de amostra para a Carta Convite oficial (frances) -- os MESMOS
dados que aparecem no PDF oficial fornecido pelo projeto (ver
pdfengine/assets/fr/Modelo-Carta-Convite-FR.pdf), usados para os testes
do renderer e para a ferramenta de preview visual
(pdfengine/tools/render_preview.py).

Usar exatamente estes valores permite comparar o PDF GERADO com o PDF
OFICIAL lado a lado -- qualquer diferenca de posicionamento fica visivel
de imediato, porque o texto deveria terminar no mesmo lugar.
"""

FR_SAMPLE_DATA = {
    "host_name": "Claire Dubois",
    "host_birth": "14/03/1985",
    "host_nationality": "belge",
    "host_document_type": "belge",
    "host_document": "00000000",
    "host_address": "Rue des Exemple 25 - 1200 Woluwe-Saint-Lambert",
    "host_phone": "+32 470 00 00 00",
    "guest_name": "Carlos Eduardo Silva",
    "guest_nationality": "Brésilienne",
    "guest_birth": "22/07/1990",
    "guest_passport": "YY000000",
    "arrival_date": "10/10/2026",
    "departure_date": "24/10/2026",
    "duration_days": "15",
    "place": "Woluwe-Saint-Lambert",
    "document_date": "09/09/2026",
    "signature_name": "Claire Dubois",
}
