# Desenrola

Aplicacao web para geracao de Carta Convite.

- **Dominio:** desenrola.be
- **Idiomas:** portugues, frances, holandes, ingles
- **Stack:** Python 3.13 / Django 5.2 LTS / PostgreSQL / HTML, CSS, JavaScript
- **Deploy:** PythonAnywhere

---

## Estado atual

Fundacao tecnica. O que existe:

- projeto Django com settings separados por ambiente;
- User customizado com login por e-mail;
- cinco apps criados e registrados;
- i18n configurado nos quatro idiomas, com prefixo de idioma nas URLs;
- login e logout nativos ligados (templates provisorios);
- suite de testes cobrindo as decisoes de fundacao.

Ainda **nao** implementado: geracao de PDF, formulario da carta, modelos de
documento, permissoes granulares, dashboard definitivo, layout visual,
compartilhamento por WhatsApp e envio real de e-mail.

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
