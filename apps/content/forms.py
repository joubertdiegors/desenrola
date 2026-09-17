"""
O formulário de edição de uma seção, montado a partir de `section_schema`.

COMO FUNCIONA
-------------
A declaração diz quais textos a seção tem; este módulo transforma isso
num `forms.Form` de verdade, com um campo por texto. Nada de um
`Textarea` com JSON dentro: quem edita a Home escreve num campo chamado
"Título principal", não num objeto.

O QUE ELE NÃO TOCA
------------------
`salvar()` parte do conteúdo que já está gravado e sobrescreve APENAS as
chaves declaradas. Tudo o mais -- o `icon` de cada cartão, e qualquer
chave que uma etapa futura acrescente -- atravessa intacto. Isso é o que
permite a tela editar o texto de um cartão sem apagar o ícone dele.

LISTAS
------
Um cartão vira campos achatados (`cards__0__title`), um conjunto por
item EXISTENTE. A tela edita os cartões que há; acrescentar ou remover é
mudança de estrutura, e estrutura mora no template.
"""

import copy

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Asset, FaqItem, MenuItem, PageSection, Partner
from .section_schema import Lista, campos_da_secao, secao_declarada
from .services import ANCORAS_DA_HOME

# Separa as partes do nome de um campo de lista: `cards__0__title`.
SEPARADOR = "__"


def _nome_do_item(lista, indice, campo):
    return f"{lista.chave}{SEPARADOR}{indice}{SEPARADOR}{campo.chave}"


def _widget(texto):
    if texto.longo:
        return forms.Textarea(attrs={"class": "input", "rows": 3})
    return forms.TextInput(attrs={"class": "input"})


def _campo(texto, valor):
    return forms.CharField(
        label=texto.rotulo,
        help_text=texto.ajuda,
        required=False,
        initial=valor,
        widget=_widget(texto),
        validators=list(texto.validators),
    )


class FormularioDeSecao(forms.Form):
    """
    Os textos de uma seção, num idioma.

    Todos os campos são opcionais: uma tradução pela metade é um estado
    legítimo -- e apagar um texto é uma decisão editorial, não um erro
    de preenchimento. O template já lida com texto ausente.
    """

    # Os campos que NÃO vão para o JSON da tradução: são colunas da
    # seção, e valem em todos os idiomas.
    DA_SECAO = (
        "layout",
        "imagem_upload",
        "imagem",
        "imagem_remover",
        "contador_ativo",
        "contador_posicao",
        "contador_ao_vivo_ativo",
        "parceiros_posicao_botao",
        "parceiros_ver_todos_ativo",
    )

    def __init__(self, secao, conteudo=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.secao = secao
        self.conteudo_atual = copy.deepcopy(conteudo or {})
        self.grupos = []
        self._montar_campos_da_secao(secao)

        for declaracao in campos_da_secao(secao):
            if isinstance(declaracao, Lista):
                self._montar_lista(declaracao)
            else:
                self.fields[declaracao.chave] = _campo(
                    declaracao, self.conteudo_atual.get(declaracao.chave, "")
                )

    def _montar_campos_da_secao(self, secao):
        """
        O desenho e a imagem -- só para as seções que declaram ter.

        Uma seção com um desenho só não ganha um seletor de um item, e
        uma sem imagem não ganha um campo de imagem: campo que não
        oferece escolha é ruído na tela.
        """
        declarada = secao_declarada(secao)

        if len(declarada.layouts) > 1:
            self.fields["layout"] = forms.ChoiceField(
                label=_("Desenho"),
                required=False,
                initial=declarada.layout_ou_padrao(secao.layout).chave,
                choices=[(layout.chave, layout.nome) for layout in declarada.layouts],
                help_text=_(
                    "Como esta parte é montada. A pré-visualização ao lado "
                    "responde na hora."
                ),
                widget=forms.Select(attrs={"class": "input"}),
            )

        if declarada.imagem:
            self.fields["imagem_upload"] = forms.ImageField(
                label=_("Enviar uma imagem nova"),
                required=False,
                widget=forms.ClearableFileInput(
                    attrs={"class": "input", "accept": "image/*", "data-preview-de-imagem": "1"}
                ),
                help_text=_(
                    "PNG, JPEG, GIF ou WEBP, até 3 MB. Substitui a imagem "
                    "escolhida abaixo -- não é preciso passar pela "
                    "Biblioteca Central primeiro."
                ),
            )
            self.fields["imagem"] = forms.ModelChoiceField(
                label=_("Ou escolher uma imagem já existente na Biblioteca"),
                required=False,
                initial=secao.image_id,
                queryset=Asset.objects.filter(is_active=True),
                empty_label=_("Sem imagem (mostra a moldura vazia)"),
                widget=forms.Select(attrs={"class": "input"}),
            )
            if secao.image_id:
                self.fields["imagem_remover"] = forms.BooleanField(
                    label=_("Remover a imagem atual"), required=False
                )

        if declarada.contador:
            self.fields["contador_ativo"] = forms.BooleanField(
                label=_("Mostrar o contador de cartas"),
                required=False,
                initial=secao.counter_enabled,
                help_text=_(
                    "O número vem sempre do sistema (cartas realmente "
                    "emitidas) -- não é editável."
                ),
            )
            self.fields["contador_posicao"] = forms.ChoiceField(
                label=_("Posição do contador"),
                required=False,
                initial=secao.counter_position,
                choices=PageSection.Posicao9.choices,
                widget=forms.Select(attrs={"class": "input"}),
            )
            self.fields["contador_ao_vivo_ativo"] = forms.BooleanField(
                label=_("Mostrar o indicador \"ao vivo\""),
                required=False,
                initial=secao.counter_live_enabled,
            )

        if declarada.cartoes_com_botao:
            self.fields["parceiros_posicao_botao"] = forms.ChoiceField(
                label=_("Posição do botão no cartão"),
                required=False,
                initial=secao.partners_button_position,
                choices=PageSection.Posicao9.choices,
                widget=forms.Select(attrs={"class": "input"}),
            )
            self.fields["parceiros_ver_todos_ativo"] = forms.BooleanField(
                label=_("Botão \"Ver todos os parceiros\""),
                required=False,
                initial=secao.partners_view_all_enabled,
                help_text=_(
                    "Aparece quando há mais de 4 parceiros cadastrados e leva "
                    "à página com todos eles."
                ),
            )

    def clean_imagem_upload(self):
        return _validar_arquivo_de_imagem(self.cleaned_data.get("imagem_upload"))

    def _montar_lista(self, lista):
        """Um conjunto de campos por item já existente no conteúdo."""
        itens = self.conteudo_atual.get(lista.chave) or []
        nomes = []
        for indice, item in enumerate(itens):
            if not isinstance(item, dict):
                continue
            do_item = []
            for texto in lista.campos:
                nome = _nome_do_item(lista, indice, texto)
                self.fields[nome] = _campo(texto, item.get(texto.chave, ""))
                do_item.append(nome)
            nomes.append(do_item)
        if nomes:
            self.grupos.append({"rotulo": lista.rotulo, "itens": nomes})

    def campos_soltos(self):
        """Os textos que não pertencem a nenhuma lista, na ordem declarada."""
        de_lista = {nome for grupo in self.grupos for item in grupo["itens"] for nome in item}
        fora = de_lista | set(self.DA_SECAO)
        return [self[nome] for nome in self.fields if nome not in fora]

    def campos_da_parte(self):
        """
        Desenho e imagem -- os que não são texto, e vão na própria seção.

        Nome diferente de `campos_da_secao`, a função do schema que este
        módulo importa: dois nomes iguais para coisas diferentes é
        confusão garantida na próxima leitura.
        """
        return [self[nome] for nome in self.DA_SECAO if nome in self.fields]

    def aplicar_na_secao(self, secao):
        """
        Grava desenho e imagem NA SEÇÃO, e diz se algo mudou.

        Separado de `conteudo()` de propósito: aquilo é o JSON de UM
        idioma, isto é a parte inteira. Misturar os dois faria trocar o
        desenho em português deixar o francês com outro.
        """
        mudou = []
        if "layout" in self.fields:
            escolhido = self.cleaned_data.get("layout") or ""
            if secao.layout != escolhido:
                secao.layout = escolhido
                mudou.append("layout")
        if "imagem" in self.fields:
            # Upload novo vence a selecao da biblioteca, que vence
            # "remover", que vence manter a imagem gravada -- mesma
            # ordem de `FormularioDeParceiro.save()`. A limpeza da
            # imagem ANTERIOR quando ela fica orfa e' responsabilidade
            # de quem chama este metodo (a view conhece o `image_id` de
            # antes de `aplicar_na_secao` rodar).
            novo_arquivo = self.cleaned_data.get("imagem_upload")
            if novo_arquivo:
                imagem = Asset.objects.create(
                    file=novo_arquivo, kind=Asset.Kind.HOME, alt_text=secao.key or secao.kind
                )
            elif self.cleaned_data.get("imagem_remover"):
                imagem = None
            else:
                imagem = self.cleaned_data.get("imagem")
            if secao.image_id != (imagem.pk if imagem else None):
                secao.image = imagem
                mudou.append("image")
        if "contador_ativo" in self.fields:
            ativo = bool(self.cleaned_data.get("contador_ativo"))
            if secao.counter_enabled != ativo:
                secao.counter_enabled = ativo
                mudou.append("counter_enabled")
        if "contador_posicao" in self.fields:
            posicao = (
                self.cleaned_data.get("contador_posicao")
                or PageSection.Posicao9.SUPERIOR_ESQUERDA
            )
            if secao.counter_position != posicao:
                secao.counter_position = posicao
                mudou.append("counter_position")
        if "contador_ao_vivo_ativo" in self.fields:
            ao_vivo = bool(self.cleaned_data.get("contador_ao_vivo_ativo"))
            if secao.counter_live_enabled != ao_vivo:
                secao.counter_live_enabled = ao_vivo
                mudou.append("counter_live_enabled")
        if "parceiros_posicao_botao" in self.fields:
            posicao = (
                self.cleaned_data.get("parceiros_posicao_botao")
                or PageSection.Posicao9.INFERIOR_CENTRO
            )
            if secao.partners_button_position != posicao:
                secao.partners_button_position = posicao
                mudou.append("partners_button_position")
        if "parceiros_ver_todos_ativo" in self.fields:
            ativo = bool(self.cleaned_data.get("parceiros_ver_todos_ativo"))
            if secao.partners_view_all_enabled != ativo:
                secao.partners_view_all_enabled = ativo
                mudou.append("partners_view_all_enabled")
        if mudou:
            secao.save(update_fields=[*mudou, "updated_at"])
        return bool(mudou)

    def grupos_de_itens(self):
        """Os grupos de lista, com os BoundField já resolvidos."""
        return [
            {
                "rotulo": grupo["rotulo"],
                "itens": [[self[nome] for nome in item] for item in grupo["itens"]],
            }
            for grupo in self.grupos
        ]

    def conteudo(self):
        """
        O dicionário a gravar: o que já existia, com os textos
        declarados por cima.
        """
        novo = copy.deepcopy(self.conteudo_atual)

        for declaracao in campos_da_secao(self.secao):
            if isinstance(declaracao, Lista):
                itens = novo.get(declaracao.chave) or []
                for indice, item in enumerate(itens):
                    if not isinstance(item, dict):
                        continue
                    for texto in declaracao.campos:
                        nome = _nome_do_item(declaracao, indice, texto)
                        if nome in self.cleaned_data:
                            item[texto.chave] = self.cleaned_data[nome]
            else:
                novo[declaracao.chave] = self.cleaned_data.get(declaracao.chave, "")

        return novo


class FormularioDeParceiro(forms.ModelForm):
    """
    O cadastro de um parceiro, no Backoffice.

    POR QUE UM `ModelForm`, E NAO UM FORMULARIO DECLARADO
    ----------------------------------------------------
    Aqui os campos SAO as colunas do modelo -- nome, descrição, logo,
    endereço, situação e ordem. `FormularioDeSecao` é declarativo porque
    o que ele edita mora num JSON sem colunas; este não tem esse
    problema, e repetir a declaração à mão só criaria dois lugares para
    mudar quando uma coluna mudasse.

    A IMAGEM CONTINUA SENDO UM `Asset` (Bloco D)
    ---------------------------------------------
    Nao ha `ImageField` no modelo `Partner` -- toda imagem administrável
    do projeto continua morando em `content.Asset`, inclusive com a
    proteção contra trocar o arquivo do qual uma carta finalizada
    depende. O que muda aqui é SÓ a tela: `logo_upload` cria o `Asset`
    na hora, sem passar pela Biblioteca Central primeiro -- `save()`,
    abaixo, é quem faz essa ponte. `logo` (o seletor) continua existindo
    para quem realmente quer reaproveitar uma imagem já cadastrada, mas
    deixou de ser o caminho obrigatório.

    Só as ATIVAS no seletor: oferecer uma imagem desativada seria
    oferecer algo que não se quer mais usar.
    """

    # Declarado a mao so por causa de `assume_scheme`: o Django 6 vai
    # trocar o padrao de http para https, e o aviso de depreciacao pede
    # que a escolha seja explicita. Mesmo caminho ja tomado em
    # `core.forms` para os enderecos das redes sociais. O rotulo e a
    # ajuda continuam vindo do modelo -- nao ha segundo lugar para mudar.
    url = forms.URLField(
        label=Partner._meta.get_field("url").verbose_name,
        help_text=Partner._meta.get_field("url").help_text,
        required=False,
        assume_scheme="https",
        widget=forms.URLInput(attrs={"class": "input"}),
    )
    logo_upload = forms.ImageField(
        label=_("Imagem/logo"),
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"class": "input", "accept": "image/*", "data-preview-de-imagem": "1"}
        ),
        help_text=_("PNG, JPEG, GIF ou WEBP, até 3 MB. Substitui o que estiver escolhido abaixo."),
    )
    class Meta:
        model = Partner
        fields = ("name", "description", "logo", "url", "is_active", "order")
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"class": "input", "rows": 3}),
            "logo": forms.Select(attrs={"class": "input"}),
            "order": forms.NumberInput(attrs={"class": "input", "min": 0}),
        }
        labels = {"logo": _("Ou escolher uma imagem já existente na Biblioteca")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["logo"].required = False
        self.fields["logo"].queryset = Asset.objects.filter(is_active=True)
        self.fields["logo"].empty_label = _("Sem imagem")
        # So oferece "remover" para quem ja tem imagem -- cadastrando um
        # parceiro novo, sem logo nenhuma ainda, o campo seria ruido.
        if self.instance.pk and self.instance.logo_id:
            self.fields["logo_remover"] = forms.BooleanField(
                label=_("Remover a imagem atual"), required=False
            )
        # `logo_upload` e `logo_remover` sao so DECLARADOS (nao estao em
        # `Meta.fields`), entao o Django os poe no fim da lista por
        # padrao -- depois de "Ordem". Reordenado aqui para o upload
        # ficar junto do resto da identificacao do parceiro, como
        # "Escolher uma imagem" ja fica.
        self.order_fields(
            [
                "name",
                "description",
                "logo_upload",
                "logo",
                "logo_remover",
                "url",
                "is_active",
                "order",
            ]
        )

    def clean_logo_upload(self):
        return _validar_arquivo_de_imagem(self.cleaned_data.get("logo_upload"))

    def save(self, commit=True):
        """
        Resolve a imagem final ANTES de gravar: upload novo vence
        seleção da biblioteca, que vence "remover", que vence manter o
        que já estava. A limpeza da imagem ANTERIOR (quando ela fica
        órfã) é responsabilidade de quem chama `save()` -- a view, que é
        quem sabe qual era o `Partner.logo_id` antes deste método rodar.
        """
        parceiro = super().save(commit=False)
        novo_arquivo = self.cleaned_data.get("logo_upload")
        if novo_arquivo:
            parceiro.logo = Asset.objects.create(
                file=novo_arquivo, kind=Asset.Kind.PARTNER, alt_text=parceiro.name
            )
        elif self.cleaned_data.get("logo_remover"):
            parceiro.logo = None
        if commit:
            parceiro.save()
        return parceiro


class FormularioDeItemDoMenu(forms.ModelForm):
    """
    Um item da barra superior do site.

    O DESTINO É CONFERIDO DUAS VEZES
    --------------------------------
    O validador do modelo (`DESTINO_DO_MENU`) cuida da FORMA: âncora,
    caminho do site ou endereço http(s) -- nada de `javascript:`, que
    terminaria dentro de um `href`, onde o autoescape não protege.

    Aqui se confere o SENTIDO: uma âncora só é aceita se a Home
    realmente a desenha. `#promoções` passa na forma e é um link morto
    na prática, e link que não leva a lugar nenhum é o defeito que este
    projeto remove desde a Etapa G.

    Caminho e endereço externo não são conferidos aqui: o servidor não
    tem como saber o que existe do outro lado, e fingir que sabe seria
    pior do que não conferir.
    """

    class Meta:
        model = MenuItem
        fields = ("label", "destination", "is_active", "order")
        widgets = {
            "label": forms.TextInput(attrs={"class": "input"}),
            "destination": forms.TextInput(attrs={"class": "input", "list": "ancoras-da-home"}),
            "order": forms.NumberInput(attrs={"class": "input", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destination"].help_text = _(
            "Uma parte da página inicial (%(ancoras)s), um caminho do site "
            "(/pt/...) ou um endereço http(s)."
        ) % {"ancoras": ", ".join(sorted(ANCORAS_DA_HOME))}

    def clean_destination(self):
        destino = (self.cleaned_data.get("destination") or "").strip()
        if destino.startswith("#") and destino not in ANCORAS_DA_HOME:
            raise forms.ValidationError(
                _(
                    "A página inicial não tem esta parte. As âncoras possíveis "
                    "são: %(ancoras)s."
                )
                % {"ancoras": ", ".join(sorted(ANCORAS_DA_HOME))}
            )
        return destino


class FormularioDePergunta(forms.ModelForm):
    """
    Uma pergunta frequente da Home.

    PERGUNTA E RESPOSTA SÃO TEXTO SIMPLES
    -------------------------------------
    A resposta é `<textarea>`, e o template a desenha com
    `|linebreaks`: parágrafos saem de linhas em branco, e nada mais. Não
    há editor de formatação aqui, e é de propósito -- HTML digitado por
    quem administra seria HTML cru dentro da Home, que é exatamente o
    que o projeto não aceita sem sanitização.

    A ORDEM NÃO SE DIGITA NA PRÁTICA
    --------------------------------
    O campo existe e funciona, mas quem administra usa as setas da
    lista, que renumeram tudo pela posição (ver `_reordenar`). Deixá-lo
    na tela é o que permite pôr uma pergunta no meio sem subir seis
    vezes.

    NÃO HÁ `clean_question` NEM `clean_answer` AQUI
    -----------------------------------------------
    Havia, e eram código morto: `forms.CharField` já apara os espaços
    das pontas antes de conferir o preenchimento, então `"   "` chega
    ao `clean_` como vazio -- e o campo obrigatório já o recusou. Os
    dois métodos nunca chegavam a rodar, e uma mutação deliberada
    mostrou isso: apagá-los não mudou resposta nenhuma da tela. O que
    guarda a regra são os testes, não um método que nunca executa.
    """

    class Meta:
        model = FaqItem
        fields = ("question", "answer", "is_active", "order")
        widgets = {
            "question": forms.TextInput(attrs={"class": "input"}),
            "answer": forms.Textarea(attrs={"class": "input", "rows": 6}),
            "order": forms.NumberInput(attrs={"class": "input", "min": 0}),
        }


# O limite de tamanho de uma imagem enviada pelo Backoffice.
#
# 3 MB e folgado para o que estas imagens sao -- logotipo, foto de banner,
# marca de parceiro -- e apertado o bastante para nao encher o disco do
# servidor com a foto que saiu direto da camera.
TAMANHO_MAXIMO_DA_IMAGEM = 3 * 1024 * 1024

# Os formatos que o site sabe servir.
#
# `ImageField` ja recusa o que nao for imagem de verdade: o Pillow tenta
# ABRIR o arquivo, entao um .exe renomeado para .png nao passa. Esta
# lista existe para o passo seguinte -- recusar formatos que o Pillow ate
# abre mas que nao queremos servir. SVG fica de fora de proposito: nao e
# bitmap, o Pillow nao o abre, e e um vetor de XSS por poder trazer
# <script> dentro.
FORMATOS_ACEITOS = ("PNG", "JPEG", "GIF", "WEBP")


def _validar_arquivo_de_imagem(arquivo):
    """
    Tamanho e formato REAL do arquivo -- as mesmas regras em todo lugar
    que aceita upload (Biblioteca, Parceiros, Banners).

    Um lugar só para esta checagem: `FormularioDeImagem.clean_file()` e
    os campos de upload embutido em `FormularioDeParceiro` e
    `FormularioDeSecao` (Bloco D) chamam esta função em vez de repetir
    as duas condições cada um a seu modo.

    O atributo `accept` do HTML é só atalho de tela -- quem manda um
    arquivo por fora do navegador nunca passa por ele. `ImageField` já
    recusou o que o Pillow não consegue abrir como imagem antes desta
    função rodar; aqui é só tamanho e formato.
    """
    if arquivo is None or not hasattr(arquivo, "image"):
        return arquivo

    if arquivo.size > TAMANHO_MAXIMO_DA_IMAGEM:
        raise forms.ValidationError(
            _("A imagem tem %(tem)s MB e o limite é %(limite)s MB.")
            % {
                "tem": round(arquivo.size / 1024 / 1024, 1),
                "limite": TAMANHO_MAXIMO_DA_IMAGEM // 1024 // 1024,
            }
        )

    formato = getattr(arquivo.image, "format", None)
    if formato not in FORMATOS_ACEITOS:
        raise forms.ValidationError(
            _("Formato %(formato)s não aceito. Use: %(aceitos)s.")
            % {
                "formato": formato or _("desconhecido"),
                "aceitos": ", ".join(FORMATOS_ACEITOS),
            }
        )
    return arquivo


class FormularioDeImagem(forms.ModelForm):
    """
    Uma imagem da biblioteca.

    `key` NAO entra aqui de proposito: e o identificador fixo com que o
    codigo encontra certas imagens (o logotipo, o favicon). Deixa-lo
    editavel numa tela de cadastro seria oferecer a qualquer pessoa a
    chance de renomear o logotipo do site para outra coisa e o site
    parar de o encontrar. Quem precisa disso usa a administração do
    Django, que e onde essa decisão rara cabe.
    """

    class Meta:
        model = Asset
        fields = ("file", "kind", "alt_text", "is_active")
        widgets = {
            "kind": forms.Select(attrs={"class": "input"}),
            "alt_text": forms.TextInput(attrs={"class": "input"}),
        }

    def clean_file(self):
        # Na edicao sem trocar o arquivo, o que chega e o `FieldFile` que
        # ja esta no disco -- nao ha envio para conferir (a funcao
        # devolve sem checar quando nao ha `.image` para olhar).
        return _validar_arquivo_de_imagem(self.cleaned_data.get("file"))
