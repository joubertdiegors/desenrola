# Auditoria do CMS e do site público

Levantamento somente de leitura do site público, do Backoffice e da infraestrutura
de conteúdo, com a sequência de implementação para tornar administrável o que hoje
está no código.

| | |
|---|---|
| **Projeto** | Desenrola · Django 5.2 · Python 3.13 |
| **HEAD auditado** | `9cd2644` — *feat: add secure email configuration to backoffice* |
| **Suíte no momento da auditoria** | 2 238 testes verdes |
| **Alcance** | Somente leitura: nenhum arquivo alterado, nenhuma migration criada, nenhum commit |

---

## Sumário

1. [Resumo executivo](#1-resumo-executivo)
2. [Inventário das páginas](#2-inventário-das-páginas)
3. [Home — inventário detalhado](#3-home--inventário-detalhado)
4. [Backoffice — situação atual](#4-backoffice--situação-atual)
5. [Nacionalidades](#5-nacionalidades)
6. [Datas](#6-datas)
7. [Contador da Home](#7-contador-da-home)
8. [Arquitetura CMS proposta](#8-arquitetura-cms-proposta)
9. [Roadmap de implementação](#9-roadmap-de-implementação)
10. [Riscos e dependências](#10-riscos-e-dependências)

---

## 1. Resumo executivo

Quatro achados decidem o desenho da próxima etapa.

### 1. O CMS já está construído e está órfão

`apps/content` tem `Asset`, `ContentBlock` + `ContentTranslation`, `Page` +
`PageSection` + `PageSectionTranslation` e `SiteSettings` — tabelas criadas
(migrations `0001_initial` e `0002_cms_assets_pages_settings`), admin Django
registrado, cerca de 40 testes de modelo.

**Nenhuma view, template ou context processor lê qualquer um desses modelos.**
A única exceção é `Asset`, consumido por `doctemplates` (editor estrutural,
`layout_schema`, geração de PDF, comando `reconstruir_modelos_oficiais`). O
projeto não tem nenhum context processor próprio — `config/settings/base.py`
lista apenas os quatro do Django.

Consequência prática: a próxima etapa é **ligar** o que existe, não projetar um CMS.

### 2. Não existe model `Partner`

Os parceiros da Home vêm de `demo.PARTNERS` (4 dicionários fixos) e o Backoffice
de `demo.ADMIN_PARTNERS`. Os botões "Novo parceiro", "Editar" e "Remover" em
`templates/backoffice/partners.html` são `<button type="button">` sem `action`,
sem `form` e sem view. É a única área do escopo que precisa de um modelo novo.

### 3. Aparência tem duas representações incompatíveis e nenhuma chega ao site

- `SiteSettings.theme_primary_color` / `theme_success_color` guardam **hex**
  (`#1a5fd6`, `#17a34a`) que ninguém lê.
- `static/js/theme.js` aplica **classes nomeadas** (`t-roxo`, `s-azul`) no
  `<html>`, lidas do `localStorage` **do navegador de quem edita**.
- `templates/base.html` (linhas 12–20) repete essa leitura num script inline,
  antes do primeiro paint.

A escolha do administrador não sai da máquina dele.

### 4. Cinco itens do menu do Backoffice são vitrine

Conteúdo, Parceiros, Idiomas, Aparência e Sistema. Quatro deles — *Conteúdo*,
*Idiomas*, *Sistema* e a rota órfã *Modelos* — são a **mesma view**
`core.views.backoffice_templates` renderizando **o mesmo template**
`templates/backoffice/templates.html`, com âncoras diferentes.

### O que já é real

Visão geral, Usuários e permissões, Cartas, Modelos, Política das cartas e E-mail.
Seis telas com view própria, permissão própria verificada no servidor e cobertura
de testes. O padrão delas é o molde para o resto:

> singleton + `ModelForm` + permissão `view_` / `change_` + rota de ativação em `POST`

---

## 2. Inventário das páginas

Todas as rotas vivem sob `i18n_patterns` (prefixo `/pt/`), exceto `/i18n/` e
`/healthz/`. Ver `config/urls.py`.

| URL | View | Template | Acesso | Conteúdo administrável hoje |
|---|---|---|---|---|
| `/pt/` | `core.views.home` | `core/home.html` | Público (logado → dashboard) | **Nenhum** — tudo hardcoded + `demo` |
| `/pt/accounts/login/` | `accounts.views.LoginView` | `registration/login.html` | Público | Nenhum |
| `/pt/accounts/signup/` | `accounts.views.signup` | `accounts/signup.html` | Público | Nenhum |
| `/pt/accounts/password-reset/` + 3 | `PasswordReset*View` | `accounts/password_reset*.html` | Público | Nenhum (o **envio** já é administrável) |
| `/healthz/` | `core.views.healthz` | — | Público | n/a |
| `/pt/dashboard/` | `core.views.dashboard` | `core/dashboard.html` | Login | Cartas do usuário — real |
| `/pt/accounts/profile/` | `accounts.views.profile` | `accounts/profile.html` | Login | Real |
| `/pt/letters/*` (6 rotas) | `letters.views` | `letters/*.html` | Login | Modelos e política — real |
| `/pt/backoffice/*` (19 rotas) | várias | `backoffice/*.html` | Permissão | ver secção 4 |
| `/pt/admin/` | Django Admin | — | `is_staff` | **Único acesso ao `apps/content` hoje** |

### Componentes compartilhados pelas páginas públicas

| Arquivo | Elemento | Origem atual | Administrável? |
|---|---|---|---|
| `components/logo.html` | Ícone Phosphor + "Desenrola" / "Carta Convite" | Marcação fixa | Sim — `SiteSettings.logo` já existe e não é lido |
| `components/site_nav.html` | "Como funciona", "Parceiros", login, signup | `gettext` + `{% url %}` | Estrutural — as âncoras acompanham as seções |
| `components/site_footer.html` | "© 2026", Termos de uso, Privacidade, Contato | Fixo — os três links são `href="#"` | **Sim, urgente** — links mortos em produção |
| `base.html` L7 | `<meta name="theme-color" content="#1a5fd6">` | Hex fixo | Sim — deveria vir de `SiteSettings` |
| `base.html` L9 | `favicon.svg` estático | Arquivo em `static/img/` | Sim — `SiteSettings.favicon` existe e não é lido |
| `base.html` L8 | `<title>` | Literal "Desenrola" + bloco por página | Sim — `SiteSettings.site_name` existe e não é lido |
| `base.html` L12–20 | Script inline que lê o tema do `localStorage` | — | Substituir por variáveis servidas pelo servidor |

### O que deve permanecer estrutural no código

- Grades, breakpoints e tokens de espaçamento em `static/css/`.
- Rotas, âncoras e o contrato `active_nav` / `mobile_nav`.
- Rótulos de **interface** (botões, mensagens de erro, rótulos de formulário) —
  já passam por `gettext` e mudam com deploy, não com conteúdo.
- O assistente de carta e o PDF: o conteúdo deles é o `field_schema` do
  `DocumentTemplate`, **que já é administrável** na biblioteca de modelos.

---

## 3. Home — inventário detalhado

`templates/core/home.html`, 94 linhas. A view passa exatamente dois valores,
ambos vindos de `apps/core/demo.py`.

| Seção | Elemento | Linha | Origem atual | Administrável? | Onde no Backoffice |
|---|---|---|---|---|---|
| **Hero** | Contador "12.458" | 16 | `demo.LANDING_STAT` (fixo) | **Não — calcular** | ver secção 7 |
| | "pessoas já utilizaram nossa ferramenta" | 17 | `gettext` | Sim | Conteúdo › Home › `hero` |
| | "Atualizado em tempo real" | 19 | `gettext` — **hoje é mentira** | Sim | Conteúdo › Home › `hero` |
| | H1 "Gere sua Carta Convite…" | 21 | `gettext` | Sim | Conteúdo › Home › `hero` |
| | Parágrafo de apoio | 22 | `gettext` | Sim | Conteúdo › Home › `hero` |
| | CTA "Criar minha conta" | 24 | `gettext` + `{% url %}` | Rótulo sim, destino não | Conteúdo › Home › `hero` |
| | "Já tem uma conta? Fazer login" | 25, 27 | `blocktranslate` | Sim | Conteúdo › Home › `hero` |
| | Arte do hero | 29–31 | `img-slot` — **não há imagem**, só um ícone e a legenda "Foto: cidade belga" | **Sim, urgente** | Conteúdo › Home › `hero` (`Asset`) |
| **Trust bar** | 3 itens: seguros / rápido / profissional | 34–40 | `gettext`, ícones fixos | Sim (texto + ícone) | Conteúdo › Home › `features` |
| **Parceiros** | H2 e subtítulo | 43–44 | `gettext` | Sim | Conteúdo › Home › `partners` |
| | Lista de parceiros | 46 | `demo.PARTNERS` — 4 fixos | **Sim** | Parceiros |
| | Link do card | 47 | `href="#"` — morto | **Sim** | Parceiros › URL |
| | Imagem do parceiro | 48 | `img-slot` placeholder | **Sim** | Parceiros › logo (`Asset`) |
| | Botão "Conheça" | 53 | `gettext` | Sim | Conteúdo › Home › `partners` |
| **Como funciona** | H2 e subtítulo | 60–61 | `gettext` | Sim | Conteúdo › Home › `features` |
| | 3 cards (ícone, título, texto) | 63–77 | `gettext`. O card 2 diz "francês, inglês ou português" — **o sistema oferece quatro idiomas** | **Sim, urgente** | Conteúdo › Home › `features` |
| **CTA final** | Título, texto, botão | 85–88 | `gettext` | Sim | Conteúdo › Home › `cta` |
| | Ícones decorativos | 83, 89 | Phosphor fixos | Estrutural | — |
| **Rodapé** | "© 2026" | 6, 10 | **Ano literal no template** | Sim — ou `{% now %}` | Sistema |
| | Termos / Privacidade / Contato | 7–9 | `href="#"` — **3 links mortos** | **Sim, urgente** | Conteúdo (`ContentBlock`) |

**Leitura:** a Home mapeia quase 1 para 1 nos tipos que `PageSection.Kind` já
define — `hero`, `features`, `partners`, `cta`. Os tipos foram desenhados para
esta página. O que falta é o consumo.

---

## 4. Backoffice — situação atual

Onze itens no menu, seis reais. Nenhuma das telas de vitrine tem permissão
própria: todas exigem apenas `core.access_backoffice`.

| Menu | Rota | View | Fonte dos dados | Estado |
|---|---|---|---|---|
| Visão geral | `/backoffice/` | `backoffice_overview` | ORM — 3 contagens | **REAL** |
| Usuários | `/usuarios/` + 3 | `accounts.backoffice_views` | ORM | **REAL** |
| Cartas | `/letters/` + 1 | `letters.backoffice_views` | ORM | **REAL** |
| Modelos | `/modelos/` + 5 | `doctemplates.library_views` | ORM | **REAL** |
| Política das cartas | `/cartas/politica/` | `backoffice_letter_policy` | `LetterPolicy` | **REAL** |
| E-mail | `/email/` + 2 | `backoffice_email_settings` | `EmailSettings` | **REAL** |
| Conteúdo do site | `/content/` | `backoffice_templates` | `<input>` com `value` fixo, **sem `<form>`** | PLACEHOLDER |
| Parceiros | `/partners/` | `backoffice_partners` | `demo.ADMIN_PARTNERS` | PLACEHOLDER |
| Idiomas | `/languages/` | `backoffice_templates` | `demo.LANGUAGES` — "97% · 3 pendentes" é inventado | PLACEHOLDER |
| Aparência | `/appearance/` | `backoffice_appearance` | `demo.THEME_*_SWATCHES` → `localStorage` | PARCIAL |
| Sistema | `/system/` | `backoffice_templates` | Texto fixo: "Backup 03:00 · ok", "Última carta há 4 min" | PLACEHOLDER |
| *(órfã)* | `/templates/` | `backoffice_templates` | Card de modelo com "Versão 2.1 · 14 campos" — arquitetura aposentada | REMOVER |

### SiteSettings — existe, ninguém lê

| Campo | Padrão | Consumidor hoje | Deveria alimentar |
|---|---|---|---|
| `site_name` | "Desenrola" | nenhum | `<title>`, logo, rodapé |
| `contact_email` / `contact_phone` / `contact_address` | vazio | nenhum | Rodapé › Contato |
| `logo` / `favicon` (FK `Asset`) | null | nenhum | `logo.html`, `base.html` |
| `social_links` (JSON) | `{}` | nenhum | Rodapé |
| `theme_primary_color` | `#1a5fd6` | nenhum | Variável CSS servida pelo servidor |
| `theme_success_color` | `#17a34a` | nenhum | Variável CSS servida pelo servidor |

### Permissões

O catálogo (`apps/accounts/admin_permissions.py`) tem 8 chaves em 4 grupos.
**Nenhuma cobre conteúdo do site.** O padrão a seguir é o de `EmailSettings`:
`default_permissions = ("view", "change")` no modelo, uma migração que concede
a quem tem `accounts.manage_users`, e a entrada no catálogo.

- **Acesso administrativo:** `core.access_backoffice`, `accounts.manage_users`
- **Modelos:** `doctemplates.view_documenttemplate`, `doctemplates.change_documenttemplate`
- **Cartas:** `letters.view_all_letters`, `letters.change_letterpolicy`
- **Sistema:** `core.view_emailsettings`, `core.change_emailsettings`
- *Faltando:* conteúdo, parceiros, aparência.

### Parceiros — o que já existe e o que falta

| Capacidade | Hoje | Falta |
|---|---|---|
| Criar | nada | Model `Partner`, `ModelForm`, view, rota, template |
| Editar | nada — botão sem `form` | Tela de detalhe |
| Ativar/desativar | nada — `status` é string do `demo` | `is_active` + rota `POST` de situação |
| Logo | nada — `img-slot` vazio | FK para `Asset` (`Kind.PARTNER` já existe) |
| URL | nada — `href="#"` | `URLField` |
| Ordem | nada — ordem do literal | `order` + `Meta.ordering` |
| Nome / descrição | nada | Traduzível? **Não** — a interface é só pt. `CharField` + `TextField` bastam |
| Remover | botão sem ação | **Não implementar.** Desativar, como em modelos e usuários |

### Aparência — o caminho até o site

1. O Backoffice oferece 5 swatches de cor principal e 4 de sucesso
   (`demo.THEME_PRIMARY_SWATCHES` / `THEME_SUCCESS_SWATCHES`), como **classes**:
   `t-roxo`, `s-azul`.
2. `theme.js` grava a escolha em `localStorage["desenrola.theme"]` e aplica as
   classes no `<html>`.
3. `base.html` repete a leitura num script inline, para não piscar.
4. **Nada disso toca o servidor.** Os botões "Publicar tema" e "Restaurar padrão"
   são `type="button"` sem ação.
5. Quatro campos são `div.input.is-readonly` puramente decorativos: fundo da
   página, cor de erro, raio dos cantos, logotipo.

Há um descasamento de tipo a resolver: o banco guarda **hex livre**, a interface
oferece **paleta fechada**. A paleta fechada é a decisão certa (garante
contraste), mas então o campo deveria guardar a chave do swatch, ou o hex deveria
vir de um mapa fechado no código. Recomendação: manter o hex — mais flexível e já
validado por `HEX_COLOR_VALIDATOR` — e servir as variáveis CSS a partir dele.

### Idiomas

| Camada | Estado real |
|---|---|
| Interface | Travada em **pt** por `InterfaceEmPortuguesMiddleware`, que fecha as três portas (prefixo de URL, cookie, `Accept-Language`). Decisão de produto — **não mexer** |
| Documento | `pt`, `fr`, `nl`, `en`. `available_languages()` lista só os que têm modelo oficial ativo. Padrão da carta: `en` (`IDIOMA_PADRAO_DA_CARTA`) |
| i18n | `LocaleMiddleware`, `i18n_patterns`, `LOCALE_PATHS` intactos. `locale/` tem **só `pt`** — os outros três nunca foram extraídos |
| Seletores | 3 componentes (`language_selector`, `auth_lang`, `language_seg`) preservados e **incluídos em tela nenhuma**, com o motivo documentado em cada um |
| Conteúdo CMS | `ContentTranslation` e `PageSectionTranslation` já têm `language` com `choices=settings.LANGUAGES` e unicidade por idioma |

**O que a tela de Idiomas deveria controlar:** só o idioma do **documento** —
quais estão disponíveis na etapa 5, qual é o padrão, e um diagnóstico honesto
("este idioma tem modelo oficial ativo?"). A coluna "Interface 97% · 3 pendentes"
é ficção e deve sair. Enquanto o conteúdo do site for só pt, a aba de idiomas do
CMS mostra um campo por idioma mas só pt é obrigatório.

### Sistema

Hoje: quatro frases fixas, todas inventadas.

- Configurações globais que **realmente existem** e não têm dono: nome do site,
  contato, redes sociais, ano do rodapé, links legais.
- Configurações que **parecem** existir e não existem: backup, retenção de dados,
  registro de atividade. **Não inventar telas para elas.**

A área Sistema deve começar como a casa do que já existe.

---

## 5. Nacionalidades

O modelo já tem duas formas — mas por **papel**, não por **gênero**.

| Peça | Onde | O que faz |
|---|---|---|
| Model | `doctemplates.Nationality` | `code` (estável, gravado na carta), `name_pt/fr/nl/en`, `guest_form`, `host_form`, `order`, `is_active` |
| Lista | `letters/nationalities.py` | `nationality_choices()` com cache por requisição, invalidado por sinal |
| Formulário | `letters/forms.py` L221 | `type: "nationality"` → `ChoiceField`. Lista vazia → campo indisponível, **nunca texto livre** |
| PDF | `document_forms()` | Resolve as formas **uma vez**, no fechamento, e congela no snapshot |
| Administração | Django Admin | Sem tela no Backoffice |
| Dados | `0005_nationality` | **Sem seed.** A tabela nasce vazia |

### O problema real

As duas formas existentes são as duas construções do documento francês:

- `host_form` → "de nationalité **belge**" (adjetivo, minúscula, invariável na prática)
- `guest_form` → "Nationalité : **Brésilienne**" (substantivo, maiúscula)

`Brésilienne` é **feminino**. Um convidado homem deveria sair `Brésilien`. Como
só existe um `guest_form` por nacionalidade, todo convidado sai no gênero que o
administrador cadastrou. E **não existe campo de sexo do convidado** — o
`field_schema` oficial tem apenas nome, nacionalidade, data de nascimento e
passaporte.

### Alteração recomendada — sem quebrar documento emitido

Nada aqui alcança carta já fechada: o snapshot congela o texto no fechamento e
`document_forms()` não é consultado de novo. Isso é o que libera a mudança.

1. **Dois campos novos opcionais** em `Nationality`: `guest_form_f` e
   `guest_form_m`, ambos `blank=True`. O `guest_form` atual permanece como
   **fallback** — é isso que torna a migração inofensiva: nacionalidade sem as
   formas novas continua saindo exatamente como hoje.
2. **Um campo de gênero no `field_schema`**, `guest_gender`, tipo `choice`,
   **não obrigatório**. Entra por migração de dados no `field_schema` dos quatro
   modelos oficiais, como o placeholder do passaporte já entrou. Rascunho antigo
   sem o campo continua válido.
3. **Resolução em `nationalities.py`**: `guest_form_<gênero>` → `guest_form` →
   `name_pt` → `code`. Cadeia de fallback, nunca erro.
4. **Não tocar `host_form`.** "de nationalité belge" não flexiona em francês para
   a maioria das nacionalidades, e o anfitrião não carrega gênero no documento.

*Alternativa descartada:* um campo por gênero por idioma (8 colunas). Só se
justifica quando outro idioma ganhar documento oficial próprio — o limite já está
documentado no docstring do model.

---

## 6. Datas

A implementação atual é boa e tem **uma** lacuna concreta que explica o sintoma.

| Camada | Arquivo | O que faz |
|---|---|---|
| HTML | `letters/_field.html` L33–37 | `div.input-wrap.date-input` com 3 filhos: o input de texto, um `<input type="date" class="date-input-picker">` e um `<span class="date-input-open">` com o ícone |
| Widget | `letters/forms.py` L115–200 | `_RobustDateInput`, `format="%d/%m/%Y"`, `inputmode=numeric`, `maxlength=10`, `data-date-input`, `data-date-min` |
| JS | `static/js/app.js` L164–240 | Máscara ao digitar; `pointerdown` sincroniza valor e `min`; `keydown` Enter/Espaço chama `showPicker()`; `change` escreve de volta em dd/mm/aaaa |
| CSS | `components.css` L705–753 | O `input[type=date]` fica `opacity:0`, 34×34px, `z-index:2`, sobre o ícone decorativo (`z-index:1`) |
| Formato exibido | — | `dd/mm/aaaa` sempre, inclusive ao reexibir após erro em outro campo |
| Formato armazenado | `Letter.data` | ISO `YYYY-MM-DD` (JSON) |

### Por que o calendário pode não abrir

1. **A causa principal.** No Chrome e no Edge, clicar num `input[type=date]` *não*
   abre o seletor: só o `::-webkit-calendar-picker-indicator` abre. Esse
   pseudo-elemento ocupa uma fração do canto direito do input de 34px — e **não há
   nenhuma regra para ele no CSS do projeto** (verificado: zero ocorrências de
   `calendar-picker-indicator` em `static/css/`). Quem clica no ícone acerta, na
   maior parte da área, o campo e não o indicador. Nada acontece.
2. **Clicar no campo de texto nunca abre nada**, e é isso que o sintoma relatado
   descreve. Não há handler para isso — por desenho, já que ali se digita.
3. **Sem caminho de clique para `showPicker()`.** Ele só é chamado no `keydown`.
   No Firefox e no Safari desktop, onde o indicador WebKit não existe, sobra só o
   comportamento nativo de clique — que no Firefox funciona, no Safari não.
4. **Detalhe de robustez:** o handler de `pointerdown` chama
   `event.target.closest(...)` sem a guarda `&&` que o `keydown` tem. Um alvo sem
   `closest` lança e derruba o resto do handler.
5. **CSS morto:** `.date-input-open:focus-visible` nunca dispara — um `<span>` não
   recebe foco.

### Correção robusta proposta

- Estilizar `.date-input-picker::-webkit-calendar-picker-indicator` com
  `position:absolute; inset:0; width:100%; height:100%; opacity:0; cursor:pointer;`
  — passa a área clicável inteira a abrir o seletor no Chromium. **É a correção
  que resolve o caso relatado.**
- Trocar o `<span>` do ícone por `<button type="button">` que chama
  `picker.showPicker()` dentro do próprio `click` (ativação do usuário presente),
  em `try/catch`. Cobre Firefox e Safari desktop e faz o `:focus-visible` existente
  passar a funcionar.
- Manter o `input[type=date]` sobreposto para o celular — é o caminho que funciona
  em todos, e o único no Safari do iOS.
- Guardar o `closest` no `pointerdown`.
- **Nada muda em dd/mm/aaaa:** o input visível continua sendo o que se submete;
  o seletor nativo só escreve nele.

---

## 7. Contador da Home

`demo.LANDING_STAT = "12.458"` → `{{ landing_stat }}` em `home.html` L16, ao lado
do selo "Atualizado em tempo real".

### Os dados reais disponíveis

| Campo | Semântica | Serve para contar? |
|---|---|---|
| `Letter.status = GENERATED` | Estado atual | Sim, mas é estado mutável |
| `Letter.generated_at` | **Reescrito a cada `_finalize`** | Não — reedição move a data |
| `Letter.finalized_at` | **Gravado uma vez, nunca reescrito** | **Sim — é o marco de emissão** |
| `lifecycle.letter_state()` | Derivado (expirada, etc.) | Não — o passado não "desconta" |

### Critério recomendado

O rótulo atual diz **pessoas**, e o número que se quer exibir é de **cartas**.
Duas métricas, um rótulo — escolher e alinhar:

```python
# Cartas geradas
Letter.objects.filter(finalized_at__isnull=False).count()

# Pessoas atendidas
Letter.objects.filter(finalized_at__isnull=False).values("user").distinct().count()
```

`finalized_at` e não `status`: uma carta cancelada depois *foi* gerada, e o
contador de um site não deve andar para trás.

### Detalhes de execução

- **Cache.** A Home é pública e o `COUNT` roda a cada visita.
  `cache.get_or_set("home.cartas", …, 600)`. Não há `CACHES` configurado — o
  padrão é LocMem por processo, aceitável aqui.
- **Formatação.** `django.contrib.humanize` **não está em `INSTALLED_APPS`**. Ou
  adicionar, ou formatar na view.
- **"Atualizado em tempo real"** passa a ser verdade com cache de 10 min — ou o
  texto muda. Hoje é falso.
- **Sem piso mínimo.** Um `max(real, 12458)` seria o hardcoded de volta com outro
  nome. Se o número novo parecer pequeno, a decisão é de produto: esconder o selo
  até certo volume, ou assumir o número.

---

## 8. Arquitetura CMS proposta

Um modelo novo (`Partner`) e um context processor. Todo o resto já existe e só
precisa de tela e de consumo.

```
/backoffice/
├── Cartas            letters.backoffice_views          já existe
├── Modelos           doctemplates.library_views        já existe
├── Usuários          accounts.backoffice_views         já existe
├── E-mail            core.views (EmailSettings)        já existe
│
└── SITE  ← área nova, agrupando o que hoje é vitrine
    ├── Conteúdo      content.Page/PageSection/…        modelo existe, tela nova
    ├── Parceiros     content.Partner                   MODELO NOVO + tela
    ├── Aparência     content.SiteSettings.theme_*      campo existe, consumo novo
    ├── Idiomas       doctemplates.DocumentTemplate     só leitura + padrão
    └── Sistema       content.SiteSettings              campos existem, tela nova
```

### Regras de fronteira

- **Conteúdo** edita `PageSectionTranslation.content` (JSON) por tipo de seção.
  Não é um editor genérico: cada `Kind` tem um formulário com os campos daquele
  tipo — o mesmo espírito do `field_schema` dos modelos de documento.
- **Textos avulsos** (rodapé, termos, privacidade) são `ContentBlock`, que já
  existe exatamente para isso.
- **Imagens** são sempre `Asset`. Nenhum `ImageField` novo em lugar nenhum — o
  `Asset` já tem a proteção contra substituir arquivo de carta finalizada.
- **Idiomas não duplica** a lista de modelos: lê `available_languages()` e escreve
  só o padrão.
- **Sistema não inventa** backup nem retenção. Começa com o que existe: nome,
  contato, redes, links legais.
- **Um context processor** `apps.content.context_processors.site` entrega `site`
  (SiteSettings + tema) a todo template. É a peça que hoje não existe e que liga
  tudo.

---

## 9. Roadmap de implementação

A ordem importa: **A** é pré-requisito de tudo; **B** e **C** são independentes
entre si; **G**, **H** e **I** não dependem de nada e podem entrar a qualquer
momento.

### A. Fundação do CMS

Context processor + permissões + o menu SITE. Nenhuma tela nova de conteúdo ainda
— só o encanamento e a prova de que ele chega ao template.

- **Arquivos:** `apps/content/context_processors.py` (novo),
  `apps/content/services.py` (novo), `config/settings/base.py`,
  `apps/accounts/admin_permissions.py`, `templates/base.html`,
  `templates/components/logo.html`, `site_footer.html`, `backoffice/menu.html`
- **Migrations:** 1 — permissões `view_sitesettings` / `change_sitesettings`
  concedidas a quem tem `accounts.manage_users`
- **Testes:** context processor presente em toda página; `site_name` / logo /
  favicon chegando ao HTML; singleton criado na primeira leitura; permissões no
  catálogo; menu guardado
- **Depende de:** —

### B. Home real — contador e parceiros

A primeira entrega visível. Mata `demo.LANDING_STAT`, `demo.PARTNERS` e
`demo.ADMIN_PARTNERS` de uma vez.

- **Arquivos:** `apps/content/models.py` (`Partner`),
  `apps/content/backoffice_views.py` (novo), `apps/core/views.py` (home),
  `templates/core/home.html`, `templates/backoffice/partners.html`,
  `apps/core/demo.py`
- **Migrations:** 2 — `Partner` (+ suas permissões); concessão
- **Testes:** contador conta `finalized_at` e não `generated_at`; reeditar não
  duplica; cancelada continua contando; cache expira; parceiro inativo não sai na
  Home; ordem respeitada; CRUD + permissões + CSRF; parceiro sem logo não quebra
  a Home
- **Depende de:** A (context processor, para o `Asset` do logo)

### C. Aparência que chega ao site

Trocar o `localStorage` por variáveis CSS servidas pelo servidor. Depois disso o
script inline do `base.html` sai.

- **Arquivos:** `apps/core/views.py` (`backoffice_appearance`),
  `apps/content/forms.py` (novo), `templates/backoffice/appearance.html`,
  `templates/base.html`, `static/js/theme.js`, `static/css/base.css`
- **Migrations:** nenhuma — os campos já existem
- **Testes:** cor salva aparece no `<style>` de qualquer página; hex inválido
  recusado; "restaurar padrão" volta ao token; `theme-color` acompanha; permissão;
  CSRF; usuário anônimo vê o tema publicado
- **Depende de:** A

### D. Conteúdo das páginas

A maior etapa. Editor por tipo de seção, começando pela Home. Fatiável por `Kind`
se ficar grande: `hero` primeiro, depois `features`, `partners`, `cta`.

- **Arquivos:** `apps/content/section_schema.py` (novo), `apps/content/forms.py`,
  `apps/content/backoffice_views.py`, `templates/backoffice/content*.html` (novos),
  `templates/core/home.html`, `site_footer.html`
- **Migrations:** 1 de dados — semeia a Page "home" com as seções atuais como
  conteúdo inicial, para a Home não nascer vazia
- **Testes:** Home renderiza do banco; seção desativada some; seção sem tradução
  cai no pt; JSON inválido recusado; ordem respeitada; links legais do rodapé;
  permissões; CSRF
- **Depende de:** A, B (a seção `partners` consome `Partner`)

### E. Idiomas

Tela pequena e honesta: quais idiomas têm documento oficial, qual é o padrão da
carta. Sem percentuais de tradução inventados.

- **Arquivos:** `apps/content/backoffice_views.py`,
  `templates/backoffice/languages.html` (novo), `apps/letters/services.py` (ler o
  padrão do banco), `apps/core/demo.py`
- **Migrations:** 1 — `default_letter_language` em `SiteSettings`
- **Testes:** só idiomas com modelo ativo listados; trocar o padrão muda o idioma
  do rascunho novo; padrão sem modelo é recusado; permissão
- **Depende de:** A

### F. Sistema

A casa dos campos de `SiteSettings` que sobraram: contato, endereço, redes
sociais, ano do rodapé.

- **Arquivos:** `apps/content/forms.py`, `apps/content/backoffice_views.py`,
  `templates/backoffice/system.html` (novo), `site_footer.html`,
  `apps/core/demo.py` *(deve ficar vazio ao fim desta etapa)*
- **Migrations:** nenhuma se `social_links` JSON bastar
- **Testes:** contato aparece no rodapé; rede social inválida recusada; rodapé sem
  contato não quebra; permissão; CSRF
- **Depende de:** A, D (o rodapé é editado nas duas)

### G. Nacionalidades — gênero

Independente de todo o CMS. Pode entrar antes de A.

- **Arquivos:** `apps/doctemplates/models.py`, `official_templates.py`,
  `apps/letters/nationalities.py`, `apps/letters/forms.py`,
  `apps/doctemplates/admin.py`
- **Migrations:** 2 — `guest_form_f` / `guest_form_m` (ambos `blank`);
  `guest_gender` no `field_schema` dos 4 modelos oficiais
- **Testes:** **carta já finalizada continua byte a byte igual**; nacionalidade
  sem forma nova usa o `guest_form`; sem gênero informado usa o fallback; rascunho
  antigo sem o campo continua válido; `host_form` intocado
- **Depende de:** —

### H. Seletor de data

A menor etapa do roadmap e a de efeito mais imediato para quem usa.

- **Arquivos:** `static/css/components.css`, `static/js/app.js`,
  `templates/letters/_field.html`
- **Migrations:** nenhuma
- **Testes:** contrato template↔script (classes e `data-*`); a regra do indicador
  existe no CSS; o ícone é `<button>`; dd/mm/aaaa preservado na ida e na volta;
  `data-date-min` presente onde a data não pode ser passada. *O comportamento do
  calendário em si é do navegador — validar à mão nos três.*
- **Depende de:** —

### I. Movimentação do botão Backoffice

Mover o cartão `dash-backoffice` do corpo do Dashboard para junto da identidade do
usuário, no topo.

- **Arquivos:**
  - `templates/components/app_nav.html` — dropdown, entre "Perfil" e o separador (L15/16)
  - `templates/core/dashboard.html` — remover L34–42
  - `templates/components/tabbar.html` — o celular não tem dropdown: decidir entre 4º destino ou link no Perfil
  - `static/css/layout.css` — `.dash-backoffice*` (L501–504) fica morto
  - `apps/core/views.py` — `can_access_backoffice` deixa de servir só ao dashboard; usar `perms.core.access_backoffice` no template
- **Migrations:** nenhuma
- **Testes:** quem tem a permissão vê o link no menu do usuário em **todas** as
  páginas logadas; quem não tem não vê em nenhuma; o cartão sumiu do Dashboard;
  o celular tem um caminho
- **Depende de:** —

### Grafo de dependências

```
A ──┬── B ──┬── D ── F
    ├── C   │
    └── E   └── (B entrega valor sozinha)

G   H   I   independentes — qualquer momento
```

---

## 10. Riscos e dependências

### Alto — a etapa G toca o caminho do PDF

É o único item do roadmap que chega perto de documento emitido. A proteção existe
— o snapshot congela tudo no fechamento — mas o teste de regressão tem de ser
explícito: gerar uma carta antes, migrar, e comparar o **conteúdo da página** do
PDF (`PdfReader(...).pages[0].get_contents().get_data()`). Os bytes do arquivo não
servem: o reportlab embute um `/ID` aleatório.

### Médio — a etapa D pode inchar

"Editor de conteúdo por tipo de seção" é a descrição de um projeto inteiro. Fatiar
por `Kind` e entregar `hero` sozinho primeiro — a Home já melhora, e o formato do
JSON se prova antes de replicar.

### Médio — a etapa C e o primeiro paint

Servir cor por `<style>` inline no `<head>` significa que toda página passa a ler
`SiteSettings`. Cachear no context processor; e remover o script de `localStorage`
**na mesma etapa**, senão as duas fontes brigam e a antiga vence (roda antes).

### Baixo — `demo.py` é o placar

Ele deve terminar vazio ao fim de F. Enquanto sobrar constante ali, sobrou tela de
vitrine. `BACKOFFICE_SECTIONS` é a exceção legítima — é configuração de casca, não
dado fictício; convém movê-la para fora de `demo`.

### Baixo — quatro itens de menu, uma view

Desmontar `backoffice_templates` exige cuidar das quatro rotas de uma vez
(`content`, `languages`, `system`, `templates`) — a última é órfã e pode
simplesmente sair, junto com `templates/backoffice/templates.html`.

### Nota — sem dependência de i18n

A interface é só pt e o middleware garante isso. As tabelas de tradução do CMS
ficam prontas para quando não for, mas nenhuma etapa aqui depende disso — e
nenhuma altera a decisão atual.
