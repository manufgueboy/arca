---
name: borrador-correo
description: Redactar un correo y dejarlo como borrador abierto en la app Mail de la Mac, listo para revisar y enviar. Usar cuando pidan escribir, redactar o preparar un correo.
---

# Borrador de correo en Mail

1. Si falta algo esencial (destinatario, propósito), pregúntalo una vez.
2. Redacta asunto y cuerpo: claro, corto, en el tono que pida el usuario.
3. Crea el borrador con `applescript` (NO lo envíes):

```applescript
tell application "Mail"
    set m to make new outgoing message with properties {subject:"ASUNTO", content:"CUERPO", visible:true}
    tell m to make new to recipient at end of to recipients with properties {address:"correo@ejemplo.com"}
    activate
end tell
```

   Escapa comillas dobles dentro del texto con `\"`.
4. Dile al usuario que el borrador está abierto en Mail para que lo revise y lo envíe él.
