# Desenrola

Aplicacao web para geracao de Carta Convite.

- **Dominio:** desenrola.be
- **Idiomas:** portugues, frances, holandes, ingles
- **Stack:** Python 3.13 / Django 5.2 LTS / PostgreSQL / HTML, CSS, JavaScript
- **Deploy:** PythonAnywhere

---

## Estado atual

Fundacao tecnica + apresentacao visual. O que existe:

- projeto Django com settings separados por ambiente;
- User customizado com login por e-mail;
- cinco apps criados e registrados;
- i18n configurado nos quatro idiomas, com prefixo de idioma nas URLs;
- login e logout nativos ligados;
- design system (tokens, componentes, tema claro/escuro) replicado do
  arquivo de identidade visual, em `static/css/`;
- todas as telas navegaveis com dados ficticios (`apps/core/demo.py`):
  landing, entrar, criar conta, recuperar senha, dashboard, gerar carta,
  resultado/PDF, perfil e area administrativa visual;
- suite de testes cobrindo fundacao e telas.

Ainda **nao** implementado: autenticacao real das telas (o dashboard nao
exige login nesta fase), geracao de PDF, logica do formulario, modelos de
documento, permissoes granulares, compartilhamento por WhatsApp e envio
real de e-mail. O documento mostrado no resultado e um mock visual; a
reproducao do PDF oficial vira com o arquivo original.

---

## Estrutura

```
config/            projeto Django (settings/urls/wsgi)
  settings/        base.py, dev.py, prod.py
apps/
  core/            base compartilhada, dashboard, healthcheck
  accounts/        usuario customizado e autenticacao
  doctemplates/    modelos de documento e versionamento
  letters/         cartas geradas
  content/         conteudo editavel do site
pdfengine/         biblioteca pura de geracao de PDF (sem Django)
templates/         templates HTML globais
static/            CSS, JS e imagens do projeto
media/             PDFs base e cartas geradas (fora do Git)
locale/            catalogos de traducao
scripts/           utilitarios de desenvolvimento
tests/             testes de fundacao e integracao
requirements/      base.txt, dev.txt, prod.txt
```

Os apps moram em `apps/`, mas cada `AppConfig` define um `label` curto. Por
isso as referencias continuam sendo `accounts.User`, e nao `apps.accounts.User`.

---

## Como rodar

Requisito: **Python 3.13**.

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate

pip install -r requirements/dev.txt

copy .env.example .env
# edite o .env e gere uma SECRET_KEY:
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Aplicacao em http://127.0.0.1:8000/pt/ e admin em http://127.0.0.1:8000/pt/admin/.

### Telas de apresentacao

Todas aceitam os prefixos `/pt/`, `/fr/`, `/nl/` e `/en/`. Os formularios
sao simulados: "Entrar" e "Criar conta" levam ao dashboard; "Gerar Carta
Convite" leva ao resultado.

| Tela | URL |
|---|---|
| Landing | `/pt/` |
| Entrar | `/pt/accounts/login/` |
| Criar conta | `/pt/accounts/signup/` |
| Recuperar senha | `/pt/accounts/password-reset/` |
| Dashboard | `/pt/dashboard/` |
| Gerar Carta Convite | `/pt/letters/new/` (no celular, `?passo=1` a `?passo=4`) |
| Resultado / PDF | `/pt/letters/1/` |
| Perfil | `/pt/accounts/profile/` (no celular, `?secao=dados`, `senha`, `idioma`) |
| Admin visual | `/pt/backoffice/` (usuarios, permissoes, cartas, modelos, conteudo, idiomas, sistema) |

O tema claro/escuro e alternado pelo botao sol/lua na barra do dashboard,
pelo perfil ("Aparencia" no desktop, "Modo claro" no celular) e fica salvo
no navegador (`localStorage`, chave `desenrola.theme`).

### Autenticacao

Cadastro, login, logout, perfil (dados e troca de senha) e recuperacao de
senha sao reais e usam os mecanismos nativos do Django (sessao, hash de
senha, CSRF, `login_required`, tokens de recuperacao). O login e por
e-mail, sem diferenciar maiusculas; o cadastro guarda o e-mail em
minusculas e recusa duplicados.

Dashboard, gerar carta, resultado e perfil exigem login; o usuario anonimo
vai para `/<idioma>/accounts/login/?next=...`. A area visual em
`/backoffice/` exige `is_staff`.

A recuperacao de senha envia o link por e-mail. Em desenvolvimento ele sai
no console do `runserver`. Em producao, defina `EMAIL_URL` no `.env`
(ex.: `smtp+tls://usuario:senha@smtp.exemplo.com:587`) e, se quiser,
`DEFAULT_FROM_EMAIL`; sem `EMAIL_URL`, os e-mails sao apenas escritos no
log do servidor.

### Testes

```bash
pytest
```

### Linter

```bash
ruff check .
ruff format .
```

---

## Configuracao por ambiente

Nada sensivel fica no repositorio. Tudo vem do `.env` (ver `.env.example`).

| Ambiente | Modulo de settings | Banco |
|---|---|---|
| Desenvolvimento | `config.settings.dev` | SQLite por padrao, PostgreSQL se `DATABASE_URL` for definido |
| Producao | `config.settings.prod` | PostgreSQL obrigatorio |

`config.settings.prod` **recusa subir** se `DATABASE_URL` estiver ausente ou
nao apontar para PostgreSQL. Isso evita que producao rode num SQLite
esquecido.

---

## Traducoes

Os quatro idiomas estao configurados. Fluxo de trabalho:

```bash
python manage.py makemessages -l pt -l fr -l nl -l en
# traduza os arquivos em locale/<idioma>/LC_MESSAGES/django.po
python manage.py compilemessages
```

**No Windows:** `makemessages` e `compilemessages` dependem do GNU gettext,
que nao vem instalado. Para a compilacao existe alternativa sem instalar
nada:

```bash
python scripts/compile_messages.py
```

Para a extracao (`makemessages`) o gettext continua necessario.

Os `.po` sao versionados; os `.mo` sao gerados e ficam fora do Git.

---

## Notas de arquitetura

**PDF.** O PDF oficial da Carta Convite nunca sera recriado em HTML/CSS. Ele
sera usado como base e recebera uma camada com os dados variaveis,
preservando o documento original intacto. A engine (`pdfengine/`) e uma
biblioteca Python pura, sem Django, para ser testavel em isolamento.

**Versionamento de modelos.** O modelo da carta e dado, nao codigo: PDF base
e mapa de campos ficam numa versao imutavel. Alterar um modelo cria uma nova
versao, e cartas antigas permanecem ligadas a versao usada na geracao.

**Snapshot.** Cada carta guarda uma copia congelada de tudo que influenciou o
resultado, permitindo reproduzir o documento anos depois.

**Midia privada.** As cartas geradas sao privadas e serao entregues por view
autenticada. Nunca por mapeamento estatico publico.

---

## Deploy (PythonAnywhere)

Pendente. Pre-requisitos conhecidos, todos exigindo plano pago:
PostgreSQL, dominio proprio (`desenrola.be`) e SMTP de saida para a
recuperacao de senha.
