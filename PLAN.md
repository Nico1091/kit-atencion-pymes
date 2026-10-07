# Kit de atención al cliente para pymes (n8n + IA)

Canales: chat web incrustable y Telegram. WhatsApp queda excluido por decisión del dueño (política de Meta).

Producto para vender a pymes de Colombia (Cúcuta primero): instalación de 600 000 a 4 000 000 COP más mensualidad de 150 000 a 800 000 COP. También se venderá como paquete descargable (Gumroad). Todo en español de Colombia, trato de usted.

## Base existente (no romper)
`lead-sin-fuga/` ya está probada en un n8n real. Reglas que no se tocan:
- El JSON se regenera con `generar.py`; nunca se edita a mano.
- `pruebas.js` corre casos contra el propio JSON. Cada plantilla nueva lleva el mismo par.
- `lead_id` se deriva del teléfono o correo (idempotencia).
- Los nombres de campo se comparan sin diacríticos ("Teléfono" == "telefono").
- En la hoja se escribe después de avisar, nunca antes.
- El JSON lleva `id` en la raíz (lo exige `n8n import:workflow`).

## Piezas a construir (una carpeta por pieza)
1. `chat-ia/`: un widget de chat web (un `widget.js` que el negocio pega con una sola etiqueta `<script>`, sin dependencias) que habla con un webhook de n8n, y el mismo flujo atendiendo un bot de Telegram. Responde preguntas frecuentes del negocio con un modelo de lenguaje (proveedor configurable por credencial de n8n, sin claves en el JSON), detecta intención de compra y entrega el contacto a `lead-sin-fuga`. Horario de atención, traspaso a humano con la palabra "asesor", límite de mensajes por conversación para controlar costo.
2. `agenda-citas/`: el cliente pide cita por el chat web o por Telegram, se consulta disponibilidad en Google Calendar, se confirma, y se envían recordatorios 24 h y 2 h antes por correo y por Telegram. Cancelar y reprogramar por mensaje.
3. `venta/`: página de venta estática (un solo `index.html`, sin dependencias externas salvo Google Fonts), guía de instalación paso a paso en español, lista de precios en COP, y un documento de demostración con conversaciones de ejemplo para tres negocios tipo: odontología, restaurante, tienda de ropa.

## Reglas para todas las piezas
- Ninguna clave, token ni número real en el repositorio. Las credenciales se referencian por nombre de credencial de n8n.
- Pruebas que corran con `node pruebas.js` sin red.
- README de cada pieza: qué hace, qué necesita el cliente, cómo se importa, cómo se prueba.
- Redacción formal, sin frases de relleno.
