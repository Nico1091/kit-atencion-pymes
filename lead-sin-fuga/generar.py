# -*- coding: utf-8 -*-
import json, os

CODE_NORMALIZAR = r"""
// Normaliza el lead que llega por cualquier canal y decide si es utilizable.
// No escribe nada: solo transforma. Todo fallo se resuelve aqui, no mas adelante.

const cfg = $('Configuracion').first().json;
const cuerpo = $json.body ?? $json;

// Los formularios nombran los campos de mil maneras. Aceptamos los alias mas comunes.
const alias = {
  nombre:   ['nombre', 'name', 'full_name', 'fullname', 'nombre_completo', 'cliente', 'contacto'],
  telefono: ['telefono', 'phone', 'phone_number', 'celular', 'movil', 'whatsapp', 'tel'],
  email:    ['email', 'correo', 'correo_electronico', 'mail', 'e_mail'],
  mensaje:  ['mensaje', 'message', 'comentario', 'comentarios', 'consulta', 'texto', 'descripcion'],
  canal:    ['canal', 'channel', 'source', 'fuente', 'utm_source'],
  interes:  ['interes', 'producto', 'servicio', 'asunto', 'subject', 'interest'],
};

// Los formularios en espanol mandan "Telefono", "Descripcion", "Correo electronico" con tilde.
// Sin quitar los acentos aqui, el campo se pierde en silencio y el lead entra sin telefono.
function normalizarClave(clave) {
  return clave
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[\s\-.]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

function tomar(nombres) {
  for (const n of nombres) {
    for (const clave of Object.keys(cuerpo)) {
      if (normalizarClave(clave) === n && cuerpo[clave] != null && String(cuerpo[clave]).trim() !== '') {
        return String(cuerpo[clave]).trim();
      }
    }
  }
  return '';
}

// Telefono a formato internacional. Colombia: movil de 10 digitos que empieza en 3.
function normalizarTelefono(bruto, prefijoPais) {
  let d = String(bruto).replace(/[^\d+]/g, '');
  if (d.startsWith('+')) return d;
  d = d.replace(/\D/g, '');
  if (d.length === 0) return '';
  const pais = String(prefijoPais).replace(/\D/g, '');
  if (d.startsWith('00' + pais)) d = d.slice(2);
  if (d.startsWith(pais) && d.length > 10) return '+' + d;
  if (d.length === 10 && d.startsWith('3')) return '+' + pais + d;
  if (d.length === 7) return '+' + pais + '7' + d;
  if (d.length === 8 && d.startsWith('6')) return '+' + pais + d;
  return '+' + pais + d;
}

const emailValido = (e) => /^[^@\s]+@[^@\s.]+\.[^@\s]{2,}$/.test(e);

// Huella estable del lead: la misma persona siempre produce el mismo identificador.
// De aqui sale la idempotencia de todo el flujo: reenviar el formulario no crea un duplicado.
function huella(texto) {
  let h = 5381;
  for (let i = 0; i < texto.length; i++) {
    h = ((h * 33) ^ texto.charCodeAt(i)) & 0xffffffff;
  }
  return ('00000000' + h.toString(16)).slice(-8);
}

const nombre = tomar(alias.nombre);
const telefono = normalizarTelefono(tomar(alias.telefono), cfg.prefijo_pais);
const emailBruto = tomar(alias.email).toLowerCase();
const email = emailValido(emailBruto) ? emailBruto : '';
const mensaje = tomar(alias.mensaje);
const interes = tomar(alias.interes);

let canal = tomar(alias.canal).toLowerCase() || 'web';
const cabeceras = $json.headers ?? {};
if (!tomar(alias.canal) && cabeceras['user-agent'] && /whatsapp/i.test(cabeceras['user-agent'])) {
  canal = 'whatsapp';
}

// Sin una via de contacto no hay lead. Es el unico motivo de rechazo.
const contactable = telefono !== '' || email !== '';
const clave = (telefono || email).toLowerCase();

const ahora = new Date();
const fechaLocal = new Date(ahora.toLocaleString('en-US', { timeZone: cfg.zona_horaria }));

return [{
  json: {
    valido: contactable,
    motivo_rechazo: contactable ? '' : 'Falta telefono y correo: el lead no es contactable.',
    lead_id: contactable ? huella(clave) : '',
    fecha_alta: ahora.toISOString(),
    hora_local: fechaLocal.getHours(),
    dia_semana: fechaLocal.getDay(),
    nombre: nombre || 'Sin nombre',
    telefono: telefono,
    email: email,
    canal: canal,
    interes: interes,
    mensaje: mensaje,
    origen: cabeceras['referer'] ?? cuerpo.origen ?? '',
  },
}];
"""

CODE_PUNTUAR = r"""
// Puntua el lead por reglas explicitas y lo asigna a un vendedor.
// Reglas, no modelo: el dueno del negocio tiene que poder discutir cada punto.

const cfg = $('Configuracion').first().json;
const lead = $('Normalizar y validar').first().json;

let puntaje = 0;
const razones = [];

// Intencion declarada en el texto. Lo que mas correlaciona con una venta.
const texto = (lead.mensaje + ' ' + lead.interes).toLowerCase();
const senales = String(cfg.palabras_intencion).split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
const encontradas = senales.filter(p => p && texto.includes(p));
if (encontradas.length) {
  puntaje += 30 + Math.min(encontradas.length - 1, 2) * 10;
  razones.push('Pide ' + encontradas.join(', '));
}

// Canal. Quien escribe por WhatsApp espera respuesta hoy.
const pesoCanal = { whatsapp: 25, telefono: 25, llamada: 25, instagram: 15, facebook: 15, referido: 30, web: 10, formulario: 10 };
const pc = pesoCanal[lead.canal] ?? 10;
puntaje += pc;
razones.push('Canal ' + lead.canal);

// Completitud. Quien deja los dos datos de contacto quiere que lo llamen.
if (lead.telefono && lead.email) {
  puntaje += 15;
  razones.push('Dejo telefono y correo');
}
if (lead.mensaje.length > 80) {
  puntaje += 10;
  razones.push('Escribio un mensaje largo');
}
if (lead.nombre === 'Sin nombre') {
  puntaje -= 10;
  razones.push('Sin nombre');
}

// Fuera de horario no baja la calidad del lead, pero cambia lo que se le promete.
const inicio = Number(cfg.hora_inicio);
const fin = Number(cfg.hora_fin);
const diasHabiles = String(cfg.dias_habiles).split(',').map(n => Number(n.trim()));
const enHorario = diasHabiles.includes(lead.dia_semana) && lead.hora_local >= inicio && lead.hora_local < fin;

puntaje = Math.max(0, Math.min(100, puntaje));
const temperatura = puntaje >= Number(cfg.umbral_caliente) ? 'caliente'
                  : puntaje >= Number(cfg.umbral_tibio) ? 'tibio' : 'frio';

// Reparto estable: el mismo lead cae siempre en el mismo vendedor, aunque el flujo se repita.
const vendedores = String(cfg.vendedores).split(',').map(s => s.trim()).filter(Boolean);
const chats = String(cfg.chats_vendedores).split(',').map(s => s.trim()).filter(Boolean);
const indice = vendedores.length ? parseInt(lead.lead_id.slice(0, 4), 16) % vendedores.length : 0;
const vendedor = vendedores[indice] ?? 'Sin asignar';
const chat = chats[indice] ?? chats[0] ?? cfg.chat_respaldo;

return [{
  json: Object.assign({}, lead, {
    puntaje: puntaje,
    temperatura: temperatura,
    motivo_puntaje: razones.join('; '),
    vendedor: vendedor,
    chat_vendedor: chat,
    en_horario: enHorario,
    estado: 'nuevo',
    intentos_seguimiento: 0,
    ultimo_contacto: '',
    promesa: enHorario ? cfg.promesa_en_horario : cfg.promesa_fuera_horario,
  }),
}];
"""

CODE_FILTRAR = r"""
// Decide a quien hay que perseguir. Se ejecuta cada hora y no debe molestar dos veces por lo mismo.

const cfg = $('Configuracion del seguimiento').first().json;
const filas = $input.all().map(i => i.json);

const ahora = new Date();
const local = new Date(ahora.toLocaleString('en-US', { timeZone: cfg.zona_horaria }));
const diasHabiles = String(cfg.dias_habiles).split(',').map(n => Number(n.trim()));
const dentroDeHorario = diasHabiles.includes(local.getDay())
  && local.getHours() >= Number(cfg.hora_inicio)
  && local.getHours() < Number(cfg.hora_fin);

// Fuera de horario no se avisa a nadie: un recordatorio a las dos de la madrugada se ignora y ademas quema.
if (!dentroDeHorario) return [];

const esperaHoras = Number(cfg.horas_de_espera);
const maxIntentos = Number(cfg.intentos_maximos);
const pendientes = [];

for (const f of filas) {
  if (!f.lead_id) continue;
  if (String(f.estado).toLowerCase() !== 'nuevo') continue;
  const intentos = Number(f.intentos_seguimiento || 0);
  if (intentos >= maxIntentos) continue;

  const referencia = f.ultimo_contacto ? new Date(f.ultimo_contacto) : new Date(f.fecha_alta);
  if (isNaN(referencia.getTime())) continue;
  const horas = (ahora - referencia) / 36e5;
  // La espera crece en cada intento: 24 h, 48 h, 96 h. Insistir mas rapido no convierte mas.
  if (horas < esperaHoras * Math.pow(2, intentos)) continue;

  pendientes.push({
    json: Object.assign({}, f, {
      horas_sin_contacto: Math.round(horas),
      intento: intentos + 1,
      intentos_restantes: maxIntentos - intentos - 1,
      momento_aviso: ahora.toISOString(),
    }),
  });
}

// Los mas calientes y mas abandonados primero.
pendientes.sort((a, b) =>
  (Number(b.json.puntaje || 0) - Number(a.json.puntaje || 0)) ||
  (b.json.horas_sin_contacto - a.json.horas_sin_contacto));

return pendientes.slice(0, Number(cfg.tope_por_ejecucion));
"""

TEXTO_AVISO = (
    "={{ '*Lead ' + $json.temperatura.toUpperCase() + '* (' + $json.puntaje + '/100)\\n\\n'"
    " + '*' + $json.nombre + '*\\n'"
    " + ($json.telefono ? 'Telefono: ' + $json.telefono + '\\n' : '')"
    " + ($json.email ? 'Correo: ' + $json.email + '\\n' : '')"
    " + 'Canal: ' + $json.canal + '\\n\\n'"
    " + ($json.mensaje ? 'Escribio: ' + $json.mensaje + '\\n\\n' : '')"
    " + 'Por que: ' + $json.motivo_puntaje + '\\n'"
    " + 'Asignado a: ' + $json.vendedor + '\\n'"
    " + ($json.telefono ? 'Escribirle: https://wa.me/' + String($json.telefono).replace('+','') : '') }}"
)

TEXTO_RECORDATORIO = (
    "={{ '*Sin contactar hace ' + $json.horas_sin_contacto + ' horas* (aviso ' + $json.intento"
    " + ' de ' + ($json.intento + $json.intentos_restantes) + ')\\n\\n'"
    " + '*' + $json.nombre + '* - ' + $json.temperatura + ' (' + $json.puntaje + '/100)\\n'"
    " + ($json.telefono ? 'Telefono: ' + $json.telefono + '\\n' : '')"
    " + ($json.email ? 'Correo: ' + $json.email + '\\n' : '')"
    " + 'Pidio: ' + ($json.interes || $json.mensaje || 'sin detalle') + '\\n\\n'"
    " + ($json.telefono ? 'Escribirle ya: https://wa.me/' + String($json.telefono).replace('+','') + '\\n' : '')"
    " + ($json.intentos_restantes === 0 ? '\\nUltimo aviso: si nadie lo atiende, se marcara como perdido.' : '') }}"
)

CUERPO_CORREO = (
    "={{ 'Buen dia, ' + $json.nombre + '.\\n\\n'"
    " + 'Recibimos su mensaje y ya esta en manos de ' + $json.vendedor + '. ' + $json.promesa + '\\n\\n'"
    " + ($json.mensaje ? 'Esto fue lo que nos escribio:\\n' + $json.mensaje + '\\n\\n' : '')"
    " + 'Si necesita algo antes, responda este correo.\\n\\n'"
    " + $('Configuracion').first().json.negocio }}"
)


def nodo(nombre, tipo, ver, pos, params, extra=None):
    ident = nombre.lower().replace(' ', '-')
    n = {
        "parameters": params,
        "id": ident,
        "name": nombre,
        "type": tipo,
        "typeVersion": ver,
        "position": pos,
    }
    if extra:
        n.update(extra)
    return n


def cond_bool(expr):
    return {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
        "conditions": [{
            "id": "c1", "leftValue": expr, "rightValue": "",
            "operator": {"type": "boolean", "operation": "true", "singleValue": True},
        }],
        "combinator": "and",
    }


def cond_no_vacio(expr):
    return {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
        "conditions": [{
            "id": "c1", "leftValue": expr, "rightValue": "",
            "operator": {"type": "string", "operation": "notEmpty", "singleValue": True},
        }],
        "combinator": "and",
    }


CFG = "$('Configuracion').first().json"
CFGS = "$('Configuracion del seguimiento').first().json"

nodos = []

nodos.append(nodo("Lead entrante", "n8n-nodes-base.webhook", 2, [-240, 300], {
    "httpMethod": "POST",
    "path": "lead-entrante",
    "responseMode": "responseNode",
    "options": {},
}, {"webhookId": "lead-entrante-sin-fuga"}))

nodos.append(nodo("Configuracion", "n8n-nodes-base.set", 3.4, [-20, 300], {
    "mode": "manual",
    "includeOtherFields": True,
    "assignments": {"assignments": [
        {"id": "a1", "name": "id_hoja_calculo", "value": "PEGUE_AQUI_EL_ID_DE_LA_HOJA", "type": "string"},
        {"id": "a2", "name": "nombre_hoja", "value": "Leads", "type": "string"},
        {"id": "a3", "name": "negocio", "value": "Nombre del negocio", "type": "string"},
        {"id": "a4", "name": "zona_horaria", "value": "America/Bogota", "type": "string"},
        {"id": "a5", "name": "prefijo_pais", "value": "57", "type": "string"},
        {"id": "a6", "name": "hora_inicio", "value": "8", "type": "string"},
        {"id": "a7", "name": "hora_fin", "value": "18", "type": "string"},
        {"id": "a8", "name": "dias_habiles", "value": "1,2,3,4,5,6", "type": "string"},
        {"id": "a9", "name": "vendedores", "value": "Vendedor 1,Vendedor 2", "type": "string"},
        {"id": "a10", "name": "chats_vendedores", "value": "123456789,123456789", "type": "string"},
        {"id": "a11", "name": "chat_respaldo", "value": "123456789", "type": "string"},
        {"id": "a12", "name": "palabras_intencion",
         "value": "precio,cotizacion,cuanto vale,cuanto cuesta,comprar,disponible,domicilio,factura,urgente,hoy,agendar,cita,visita",
         "type": "string"},
        {"id": "a13", "name": "umbral_caliente", "value": "55", "type": "string"},
        {"id": "a14", "name": "umbral_tibio", "value": "30", "type": "string"},
        {"id": "a15", "name": "promesa_en_horario", "value": "Le respondemos en menos de 15 minutos.", "type": "string"},
        {"id": "a16", "name": "promesa_fuera_horario", "value": "Le respondemos a primera hora del proximo dia habil.", "type": "string"},
    ]},
    "options": {},
}, {"notes": "El unico nodo que toca el cliente. Nada mas abajo necesita edicion."}))

nodos.append(nodo("Normalizar y validar", "n8n-nodes-base.code", 2, [200, 300],
                  {"jsCode": CODE_NORMALIZAR.strip()}))

nodos.append(nodo("Datos suficientes", "n8n-nodes-base.if", 2.2, [420, 300],
                  {"conditions": cond_bool("={{ $json.valido }}"), "options": {}}))

nodos.append(nodo("Buscar en registro", "n8n-nodes-base.googleSheets", 4.5, [640, 200], {
    "documentId": {"__rl": True, "value": "={{ " + CFG + ".id_hoja_calculo }}", "mode": "id"},
    "sheetName": {"__rl": True, "value": "={{ " + CFG + ".nombre_hoja }}", "mode": "name"},
    "filtersUI": {"values": [{"lookupColumn": "lead_id", "lookupValue": "={{ $json.lead_id }}"}]},
    "options": {},
}, {
    "alwaysOutputData": True,
    "onError": "continueRegularOutput",
    "notes": "Si la hoja aun no tiene el lead devuelve vacio y el flujo sigue por la rama de lead nuevo.",
}))

nodos.append(nodo("Ya registrado", "n8n-nodes-base.if", 2.2, [860, 200],
                  {"conditions": cond_no_vacio("={{ $json.lead_id }}"), "options": {}}))

nodos.append(nodo("Respuesta duplicado", "n8n-nodes-base.respondToWebhook", 1.1, [1080, 80], {
    "respondWith": "json",
    "responseBody": "={{ { ok: true, duplicado: true, lead_id: $json.lead_id, mensaje: 'Este contacto ya estaba registrado. No se creo un duplicado ni se reenvio el acuse.' } }}",
    "options": {},
}, {"notes": "Idempotencia: el mismo formulario enviado dos veces no genera dos leads ni dos correos."}))

nodos.append(nodo("Respuesta datos incompletos", "n8n-nodes-base.respondToWebhook", 1.1, [640, 460], {
    "respondWith": "json",
    "responseCode": 422,
    "responseBody": "={{ { ok: false, motivo: $json.motivo_rechazo } }}",
    "options": {},
}))

nodos.append(nodo("Puntuar y asignar", "n8n-nodes-base.code", 2, [1080, 300],
                  {"jsCode": CODE_PUNTUAR.strip()}))

nodos.append(nodo("Guardar lead", "n8n-nodes-base.googleSheets", 4.5, [1300, 300], {
    "operation": "append",
    "documentId": {"__rl": True, "value": "={{ " + CFG + ".id_hoja_calculo }}", "mode": "id"},
    "sheetName": {"__rl": True, "value": "={{ " + CFG + ".nombre_hoja }}", "mode": "name"},
    "columns": {"mappingMode": "autoMapInputData", "matchingColumns": ["lead_id"], "value": {}},
    "options": {},
}, {"notes": "La hoja necesita la fila de encabezados del README, con los nombres exactos."}))

nodos.append(nodo("Avisar al vendedor", "n8n-nodes-base.telegram", 1.2, [1520, 200], {
    "chatId": "={{ $json.chat_vendedor }}",
    "text": TEXTO_AVISO,
    "additionalFields": {"parse_mode": "Markdown"},
}, {
    "onError": "continueRegularOutput",
    "notes": "Si Telegram falla, el lead ya quedo guardado. El aviso importa, pero no puede tumbar el registro.",
}))

nodos.append(nodo("Acuse al cliente", "n8n-nodes-base.gmail", 2.1, [1520, 400], {
    "sendTo": "={{ $json.email }}",
    "subject": "={{ 'Recibimos su solicitud - ' + " + CFG + ".negocio }}",
    "emailType": "text",
    "message": CUERPO_CORREO,
    "options": {},
}, {
    "onError": "continueRegularOutput",
    "notes": "Si el lead no dejo correo, este nodo falla en silencio y el flujo continua.",
}))

nodos.append(nodo("Respuesta recibido", "n8n-nodes-base.respondToWebhook", 1.1, [1740, 300], {
    "respondWith": "json",
    "responseBody": "={{ { ok: true, lead_id: $('Puntuar y asignar').first().json.lead_id, temperatura: $('Puntuar y asignar').first().json.temperatura, asignado_a: $('Puntuar y asignar').first().json.vendedor, mensaje: $('Puntuar y asignar').first().json.promesa } }}",
    "options": {},
}))

nodos.append(nodo("Cada hora", "n8n-nodes-base.scheduleTrigger", 1.2, [-240, 760], {
    "rule": {"interval": [{"field": "hours", "hoursInterval": 1}]},
}))

nodos.append(nodo("Configuracion del seguimiento", "n8n-nodes-base.set", 3.4, [-20, 760], {
    "mode": "manual",
    "includeOtherFields": False,
    "assignments": {"assignments": [
        {"id": "b1", "name": "id_hoja_calculo", "value": "PEGUE_AQUI_EL_ID_DE_LA_HOJA", "type": "string"},
        {"id": "b2", "name": "nombre_hoja", "value": "Leads", "type": "string"},
        {"id": "b3", "name": "zona_horaria", "value": "America/Bogota", "type": "string"},
        {"id": "b4", "name": "hora_inicio", "value": "8", "type": "string"},
        {"id": "b5", "name": "hora_fin", "value": "18", "type": "string"},
        {"id": "b6", "name": "dias_habiles", "value": "1,2,3,4,5,6", "type": "string"},
        {"id": "b7", "name": "horas_de_espera", "value": "24", "type": "string"},
        {"id": "b8", "name": "intentos_maximos", "value": "3", "type": "string"},
        {"id": "b9", "name": "tope_por_ejecucion", "value": "25", "type": "string"},
        {"id": "b10", "name": "chat_respaldo", "value": "123456789", "type": "string"},
    ]},
    "options": {},
}))

nodos.append(nodo("Leer leads", "n8n-nodes-base.googleSheets", 4.5, [200, 760], {
    "documentId": {"__rl": True, "value": "={{ $json.id_hoja_calculo }}", "mode": "id"},
    "sheetName": {"__rl": True, "value": "={{ $json.nombre_hoja }}", "mode": "name"},
    "options": {},
}, {"alwaysOutputData": True}))

nodos.append(nodo("Filtrar los que exigen seguimiento", "n8n-nodes-base.code", 2, [420, 760],
                  {"jsCode": CODE_FILTRAR.strip()}))

nodos.append(nodo("Uno por uno", "n8n-nodes-base.splitInBatches", 3, [640, 760],
                  {"batchSize": 1, "options": {"reset": False}}))

nodos.append(nodo("Recordar al vendedor", "n8n-nodes-base.telegram", 1.2, [900, 880], {
    "chatId": "={{ $json.chat_vendedor || " + CFGS + ".chat_respaldo }}",
    "text": TEXTO_RECORDATORIO,
    "additionalFields": {"parse_mode": "Markdown"},
}, {"onError": "continueRegularOutput"}))

nodos.append(nodo("Marcar seguimiento", "n8n-nodes-base.googleSheets", 4.5, [1140, 880], {
    "operation": "update",
    "documentId": {"__rl": True, "value": "={{ " + CFGS + ".id_hoja_calculo }}", "mode": "id"},
    "sheetName": {"__rl": True, "value": "={{ " + CFGS + ".nombre_hoja }}", "mode": "name"},
    "columns": {
        "mappingMode": "defineBelow",
        "matchingColumns": ["lead_id"],
        "value": {
            "lead_id": "={{ $json.lead_id }}",
            "intentos_seguimiento": "={{ $json.intento }}",
            "ultimo_contacto": "={{ $json.momento_aviso }}",
            "estado": "={{ $json.intentos_restantes === 0 ? 'perdido' : 'nuevo' }}",
        },
    },
    "options": {},
}, {"notes": "Se escribe DESPUES de avisar. Si el aviso falla, el intento no se consume y se reintenta la hora siguiente."}))

NOTA = (
    "## Lead sin fuga\n\n"
    "**Arriba**: entra el lead y sale el aviso en menos de un minuto.\n\n"
    "**Abajo**: se persigue solo al que nadie contesto, a las 24 h, 48 h y 96 h.\n\n"
    "Toque unicamente los dos nodos de configuracion.\n\n"
    "El mismo lead enviado dos veces no se duplica ni recibe dos correos: "
    "el identificador se calcula del telefono o del correo, no al azar."
)
nodos.append(nodo("Lea esto primero", "n8n-nodes-base.stickyNote", 1, [-620, 220],
                  {"content": NOTA, "height": 440, "width": 340, "color": 4}))

conexiones = {
    "Lead entrante": {"main": [[{"node": "Configuracion", "type": "main", "index": 0}]]},
    "Configuracion": {"main": [[{"node": "Normalizar y validar", "type": "main", "index": 0}]]},
    "Normalizar y validar": {"main": [[{"node": "Datos suficientes", "type": "main", "index": 0}]]},
    "Datos suficientes": {"main": [
        [{"node": "Buscar en registro", "type": "main", "index": 0}],
        [{"node": "Respuesta datos incompletos", "type": "main", "index": 0}],
    ]},
    "Buscar en registro": {"main": [[{"node": "Ya registrado", "type": "main", "index": 0}]]},
    "Ya registrado": {"main": [
        [{"node": "Respuesta duplicado", "type": "main", "index": 0}],
        [{"node": "Puntuar y asignar", "type": "main", "index": 0}],
    ]},
    "Puntuar y asignar": {"main": [[{"node": "Guardar lead", "type": "main", "index": 0}]]},
    "Guardar lead": {"main": [[
        {"node": "Avisar al vendedor", "type": "main", "index": 0},
        {"node": "Acuse al cliente", "type": "main", "index": 0},
    ]]},
    "Avisar al vendedor": {"main": [[{"node": "Respuesta recibido", "type": "main", "index": 0}]]},
    "Cada hora": {"main": [[{"node": "Configuracion del seguimiento", "type": "main", "index": 0}]]},
    "Configuracion del seguimiento": {"main": [[{"node": "Leer leads", "type": "main", "index": 0}]]},
    "Leer leads": {"main": [[{"node": "Filtrar los que exigen seguimiento", "type": "main", "index": 0}]]},
    "Filtrar los que exigen seguimiento": {"main": [[{"node": "Uno por uno", "type": "main", "index": 0}]]},
    "Uno por uno": {"main": [[], [{"node": "Recordar al vendedor", "type": "main", "index": 0}]]},
    "Recordar al vendedor": {"main": [[{"node": "Marcar seguimiento", "type": "main", "index": 0}]]},
    "Marcar seguimiento": {"main": [[{"node": "Uno por uno", "type": "main", "index": 0}]]},
}

wf = {
    # El CLI de n8n (import:workflow) exige un id en la raiz; la importacion por interfaz lo ignora.
    "id": "leadSinFugaPlantilla1",
    "name": "Lead sin fuga - captura, asigna y persigue",
    "nodes": nodos,
    "connections": conexiones,
    "active": False,
    "settings": {
        "executionOrder": "v1",
        "saveDataErrorExecution": "all",
        "saveManualExecutions": True,
        "timezone": "America/Bogota",
    },
    "pinData": {},
    "meta": {"templateCredsSetupCompleted": False},
    "tags": [],
}

destino = os.path.expanduser("~/Desktop/n8n-plantillas/lead-sin-fuga/lead-sin-fuga.json")
with open(destino, "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)

with open(destino, encoding="utf-8") as f:
    v = json.load(f)

nombres = {n["name"] for n in v["nodes"]}
problemas = []
for origen, sal in v["connections"].items():
    if origen not in nombres:
        problemas.append("origen inexistente: " + origen)
    for rama in sal["main"]:
        for c in rama:
            if c["node"] not in nombres:
                problemas.append("destino inexistente: " + c["node"])

alcanzados = {c["node"] for s in v["connections"].values() for r in s["main"] for c in r}
sueltos = [n["name"] for n in v["nodes"]
           if n["name"] not in alcanzados and n["name"] not in v["connections"]
           and n["type"] != "n8n-nodes-base.stickyNote"]

ids = [n["id"] for n in v["nodes"]]
print("JSON valido. Nodos:", len(v["nodes"]), "| Con salida:", len(v["connections"]))
print("Referencias rotas:", problemas or "ninguna")
print("Nodos sueltos:", sueltos or "ninguno")
print("Ids duplicados:", [i for i in set(ids) if ids.count(i) > 1] or "ninguno")
print("Bytes:", os.path.getsize(destino))
