---
name: recordatorios
description: Crear recordatorios o eventos de calendario en la Mac (apps Recordatorios y Calendario). Usar cuando digan "recuérdame", "agenda", "pon en mi calendario".
---

# Recordatorios y calendario

Fecha de hoy: está en tu prompt de sistema. Convierte "mañana", "el viernes", etc. a fecha exacta.

## Recordatorio
```applescript
tell application "Reminders"
    make new reminder with properties {name:"TEXTO", remind me date:(date "viernes, 26 de septiembre de 2026 10:00:00")}
end tell
```
Si el formato de fecha falla (depende del idioma de la Mac), constrúyela así:
```applescript
set d to current date
set year of d to 2026
set month of d to 9
set day of d to 26
set hours of d to 10
set minutes of d to 0
set seconds of d to 0
tell application "Reminders" to make new reminder with properties {name:"TEXTO", remind me date:d}
```

## Evento de calendario
Usa la misma forma de construir `d` y luego:
```applescript
tell application "Calendar"
    tell first calendar whose writable is true
        make new event with properties {summary:"TÍTULO", start date:d, end date:(d + 3600)}
    end tell
end tell
```

Confirma al usuario qué creaste y para cuándo.
