---
name: agenda
description: Crear recordatorios y eventos de calendario en la Mac.
activar: recuérdame, recuerdame, recordatorio, calendario, agenda, agéndame, cita, evento, reunión
---
1. Convierte la fecha que dijo el usuario a AAAA-MM-DD HH:MM usando "Ahora" y "Próximos días" del contexto.
   "mañana" = día siguiente; "el viernes" = el próximo viernes; sin hora → 09:00.
2. Algo que hacer o no olvidar → crear_recordatorio(texto, fecha).
   Algo con hora de inicio (cita, reunión, junta) → crear_evento(titulo, inicio, duracion_min, lugar).
3. Confirma en una línea qué creaste y para cuándo (día de la semana y hora).
