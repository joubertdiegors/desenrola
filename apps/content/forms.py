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

from .section_schema import Lista, campos_da_secao

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
    )


class FormularioDeSecao(forms.Form):
    """
    Os textos de uma seção, num idioma.

    Todos os campos são opcionais: uma tradução pela metade é um estado
    legítimo -- e apagar um texto é uma decisão editorial, não um erro
    de preenchimento. O template já lida com texto ausente.
    """

    def __init__(self, secao, conteudo=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.secao = secao
        self.conteudo_atual = copy.deepcopy(conteudo or {})
        self.grupos = []

        for declaracao in campos_da_secao(secao):
            if isinstance(declaracao, Lista):
                self._montar_lista(declaracao)
            else:
                self.fields[declaracao.chave] = _campo(
                    declaracao, self.conteudo_atual.get(declaracao.chave, "")
                )

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
        """Os campos que não pertencem a nenhuma lista, na ordem declarada."""
        de_lista = {nome for grupo in self.grupos for item in grupo["itens"] for nome in item}
        return [self[nome] for nome in self.fields if nome not in de_lista]

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
