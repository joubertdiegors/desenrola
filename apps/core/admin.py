"""
Administracao do app core.

`EmailSettings` NAO e registrada aqui de proposito. A tela dela e o
Backoffice (/backoffice/email/), que trata a senha com cuidado: campo
so de escrita, nunca de leitura. O ModelAdmin generico do Django nao
exibiria `password_encrypted` (o campo e `editable=False`), mas
bastaria alguem acrescenta-lo a `readonly_fields` para o texto cifrado
aparecer numa tela -- e sob a permissao errada, porque o Admin olha
`is_staff`, nao `core.change_emailsettings`.
"""
