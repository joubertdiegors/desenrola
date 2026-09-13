"""
Gera o PDF de um modelo para conferencia visual (Etapa 3.4).

    manage.py previa_documento carta-convite-fr --exemplo \\
        --saida previa.pdf \\
        --comparar pdfengine/assets/fr/Modelo-Carta-Convite-FR.pdf

Serve a revisao humana: produzir o documento, olhar, e -- quando ha um
original -- medir objetivamente o quanto os dois diferem em vez de
decidir no olho.

GENERICO
--------
Recebe um slug, qualquer um. Nada aqui sabe o que e uma carta convite: os
dados de exemplo vem de `services.dados_de_exemplo`, que e uma tabela por
slug, e o PDF de referencia vem por parametro.

A COMPARACAO
------------
Rasteriza as duas paginas com `pypdfium2` (ja e dependencia) e mede a
diferenca por pixel. Duas ressalvas que quem le os numeros precisa saber:

  * o antialiasing de dois renderizadores diferentes nunca coincide, e
    isso sozinho ja produz alguns por cento de diferenca nas bordas das
    letras -- diferenca que nao se ve;
  * um QR gerado do zero quase nunca tem os mesmos modulos de outro que
    codifique o mesmo texto (versao e mascara podem diferir), entao a
    area do QR conta como totalmente diferente mesmo estando certa.

Por isso o relatorio separa a metrica da pagina inteira da metrica de
uma regiao, quando se pede uma.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.doctemplates.models import DocumentTemplate
from apps.doctemplates.services import dados_de_exemplo, pdf

# Escala da rasterizacao: 2x sobre os 72pt/pol do PDF da 144 DPI, nitido
# o bastante para conferir posicao de texto sem gerar um PNG enorme.
ESCALA = 2.0

# Limiares do histograma de diferenca, para o relatorio.
LIMIARES = (16, 32, 64, 128)


class Command(BaseCommand):
    help = (
        "Gera o PDF de um modelo de documento para conferência visual e, "
        "opcionalmente, compara com um PDF de referência."
    )

    def add_arguments(self, parser):
        parser.add_argument("slug", help="slug do DocumentTemplate")
        parser.add_argument(
            "--saida", default=None,
            help="arquivo PDF a escrever (padrão: <slug>.pdf no diretório atual)",
        )
        parser.add_argument(
            "--dados", default=None,
            help='JSON com os valores ({"convidado.nome": "..."})',
        )
        parser.add_argument(
            "--exemplo", action="store_true",
            help="usa os dados de exemplo registrados para o slug",
        )
        parser.add_argument(
            "--comparar", default=None,
            help="PDF de referência para medir a diferença",
        )
        parser.add_argument(
            "--imagens", default=None,
            help="diretório onde gravar os PNGs da comparação",
        )

    def handle(self, *args, **opcoes):
        modelo = self._modelo(opcoes["slug"])
        dados = self._dados(modelo, opcoes)

        # Fora do modo estrito: uma previa com campos em branco ainda
        # mostra a estrutura, e e melhor do que nao gerar nada.
        conteudo, relatorio = pdf.render_template(modelo, dados, estrito=False)

        destino = Path(opcoes["saida"] or f"{modelo.slug}.pdf")
        destino.write_bytes(conteudo)
        self.stdout.write(
            f"{destino}  ({len(conteudo)} bytes, "
            f"{relatorio['desenhados']}/{relatorio['elementos']} elementos desenhados)"
        )
        faltando = sorted(set(pdf.campos_do_layout(modelo.layout)) - set(dados))
        if faltando:
            self.stdout.write(self.style.WARNING(
                f"  campos sem valor: {', '.join(faltando)}"
            ))

        if opcoes["comparar"]:
            self._comparar(conteudo, Path(opcoes["comparar"]), opcoes["imagens"])

    def _modelo(self, slug):
        modelo = DocumentTemplate.objects.filter(slug=slug).first()
        if modelo is None:
            raise CommandError(f'Não existe o modelo "{slug}".')
        if not (modelo.layout or {}).get("elements"):
            raise CommandError(f'O modelo "{slug}" ainda não tem layout.')
        return modelo

    def _dados(self, modelo, opcoes):
        if opcoes["dados"]:
            caminho = Path(opcoes["dados"])
            if not caminho.is_file():
                raise CommandError(f"Arquivo de dados não encontrado: {caminho}")
            return json.loads(caminho.read_text(encoding="utf-8"))
        if opcoes["exemplo"]:
            dados = dados_de_exemplo.para(modelo.slug)
            if not dados:
                self.stdout.write(self.style.WARNING(
                    f'  não há dados de exemplo para "{modelo.slug}"'
                ))
            return dados
        return {}

    def _comparar(self, conteudo, referencia, diretorio):
        if not referencia.is_file():
            raise CommandError(f"Referência não encontrada: {referencia}")

        import pypdfium2 as pdfium
        from PIL import Image, ImageChops

        def raster(dados):
            # Fechar explicitamente: o pdfium avisa no fim do processo
            # sobre documentos deixados abertos, e um comando de
            # inspecao nao deve terminar com ruido.
            documento = pdfium.PdfDocument(dados)
            try:
                return documento[0].render(scale=ESCALA).to_pil().convert("RGB")
            finally:
                documento.close()

        gerado = raster(conteudo)
        oficial = raster(referencia.read_bytes())

        # Recorta ao tamanho comum em vez de redimensionar: reamostrar
        # borraria todo o texto e a diferenca medida passaria a ser a da
        # interpolacao, nao a do documento.
        largura = min(gerado.width, oficial.width)
        altura = min(gerado.height, oficial.height)
        gerado = gerado.crop((0, 0, largura, altura))
        oficial = oficial.crop((0, 0, largura, altura))

        diferenca = ImageChops.difference(gerado, oficial).convert("L")
        histograma = diferenca.histogram()
        total = largura * altura
        media = sum(i * c for i, c in enumerate(histograma)) / total

        self.stdout.write(f"comparação com {referencia.name}  ({largura}x{altura}px)")
        self.stdout.write(f"  diferença média por pixel: {media:.2f} / 255")
        for limiar in LIMIARES:
            quantos = sum(histograma[limiar:])
            self.stdout.write(
                f"  pixels com diferença > {limiar:3d}: {quantos:8d}  "
                f"({100 * quantos / total:5.2f}%)"
            )

        if diretorio:
            pasta = Path(diretorio)
            pasta.mkdir(parents=True, exist_ok=True)
            gerado.save(pasta / "gerado.png")
            oficial.save(pasta / "referencia.png")
            ImageChops.invert(diferenca).save(pasta / "diferenca.png")
            lado = Image.new("RGB", (largura * 2 + 20, altura), (255, 255, 255))
            lado.paste(oficial, (0, 0))
            lado.paste(gerado, (largura + 20, 0))
            lado.save(pasta / "lado_a_lado.png")
            self.stdout.write(f"  imagens em {pasta}/")
