# Lead sin fuga

Captura el lead que llega por cualquier canal, lo puntúa, lo asigna a un vendedor y avisa en menos de un minuto. Después persigue solo a los que nadie contestó, a las 24, 48 y 96 horas, y marca como perdido al que agotó los avisos.

El problema que resuelve no es técnico: un negocio pequeño recibe la consulta por WhatsApp, por el formulario de la web y por Instagram, y las tres caen en sitios distintos. El que responde tarde pierde la venta contra quien respondió primero. Este flujo cierra esa fuga sin pedirle al negocio que cambie de herramientas.

## Qué necesita

Un n8n propio o en la nube, una hoja de cálculo de Google, una cuenta de Gmail para el acuse de recibo y un bot de Telegram para avisar al equipo. Nada de pago.

Credenciales a configurar: Google Sheets (OAuth2), Gmail (OAuth2) y Telegram. Las tres se conectan una vez y quedan.

## Instalación

1. Importa `lead-sin-fuga.json` en n8n: menú de la esquina, *Import from File*.
2. Crea una hoja de cálculo de Google con una pestaña llamada `Leads` y pega esta fila de encabezados en la primera fila, con los nombres exactos:

```
lead_id	fecha_alta	nombre	telefono	email	canal	interes	mensaje	origen	puntaje	temperatura	motivo_puntaje	vendedor	chat_vendedor	estado	intentos_seguimiento	ultimo_contacto	en_horario	promesa
```

3. Abre el nodo **Configuración** y rellena: el identificador de la hoja (lo que va entre `/d/` y `/edit` en su URL), el nombre del negocio, los vendedores y su identificador de chat de Telegram. Copia el identificador de la hoja también al nodo **Configuración del seguimiento**.
4. Conecta las tres credenciales en los nodos que las piden.
5. Activa el flujo y copia la dirección del webhook de producción. Esa es la que se pega en el formulario de la web, en Zapier, en Meta o donde entren los leads.

## Cómo se prueba sin esperar a un cliente real

Con el flujo activo, desde cualquier terminal:

```bash
curl -X POST "https://TU-N8N/webhook/lead-entrante" \
  -H "Content-Type: application/json" \
  -d '{"nombre":"Prueba Uno","telefono":"320 456 7890","correo":"prueba@ejemplo.com","mensaje":"Quiero saber el precio y si hacen domicilio"}'
```

Debe llegar el aviso a Telegram, aparecer la fila en la hoja y responder un JSON con la temperatura y el vendedor asignado. Repite el mismo comando: la segunda vez responde `duplicado: true`, no crea otra fila y no reenvía el correo.

## Decisiones que conviene entender antes de tocar nada

**El identificador del lead sale del teléfono o del correo, no del azar.** Es lo que hace que reenviar el formulario tres veces, o que Meta reintente el envío, no llene la hoja de duplicados ni bombardee al cliente con acuses de recibo. Si cambias esa función, se pierde esa garantía.

**Se puntúa por reglas, no con un modelo.** El dueño del negocio tiene que poder discutir cada punto: tantos por pedir precio, tantos por venir de WhatsApp, tantos por dejar los dos datos de contacto. Un modelo daría un número que nadie puede defender delante de él, y además costaría dinero por lead.

**Los nombres de campo se comparan sin acentos.** Los formularios en español mandan `Teléfono` y `Descripción`. Sin quitar los diacríticos, el campo se pierde en silencio y el lead entra sin teléfono: el flujo no falla, simplemente deja de servir. Fue el único defecto real que aparecieron las pruebas.

**La espera del seguimiento se duplica en cada intento**: 24 horas, luego 48, luego 96. Insistir más rápido no convierte más y quema el contacto.

**Fuera del horario configurado no se avisa a nadie.** Un recordatorio a las dos de la madrugada se ignora, y entrena al vendedor a silenciar el bot. Lo que sí cambia fuera de horario es la promesa que se le hace al cliente en el correo.

**Se escribe en la hoja después de avisar, nunca antes.** Si Telegram falla, el intento no se consume y se reintenta la hora siguiente. Al revés se perdería el aviso en silencio.

**El registro manda sobre el aviso.** Telegram y Gmail están marcados para continuar si fallan: un lead guardado sin aviso se recupera mirando la hoja, pero un lead que no se guardó por un fallo de Telegram no se recupera de ningún sitio.

## Qué hace el vendedor

Recibe el aviso con un enlace `wa.me` directo al teléfono ya normalizado, así que contesta con un toque. Cuando atiende al cliente, cambia a mano la columna `estado` de `nuevo` a `contactado` en la hoja. Ese es el único trabajo manual del sistema, y es deliberado: es lo que distingue un lead atendido de uno abandonado, y ninguna automatización lo puede adivinar.

## Límites conocidos

La hoja de cálculo funciona bien hasta unos pocos miles de filas; por encima de eso conviene una base de datos. El seguimiento lee la hoja completa cada hora, de modo que con volúmenes grandes hay que filtrar en la lectura. El acuse por correo solo sale si el lead dejó correo, lo cual es correcto pero significa que los leads de WhatsApp solo reciben el contacto del vendedor.

No hay respuesta automática por WhatsApp. Se podría añadir, pero exige la API de WhatsApp Business con su verificación de negocio, y eso ya no es una plantilla que alguien importa y usa el mismo día.

## Pruebas

`pruebas.js` extrae el código de los tres nodos del propio JSON y lo ejecuta contra 37 casos: teléfonos colombianos en cinco formatos, alias de campo en dos idiomas, correos inválidos, leads sin vía de contacto, duplicados, hojas vacías, filas corruptas, fechas ilegibles, cero vendedores configurados y el tope por ejecución.

```bash
node pruebas.js
```

Si modificas la lógica, corre esto antes de dárselo a un cliente. Prueba el archivo que se va a importar, no una copia, así que no puede quedar desincronizado.
