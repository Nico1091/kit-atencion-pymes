// Extrae el jsCode de los nodos Code del JSON y lo ejecuta con datos simulados.
const fs = require('fs');
const os = require('os');
const path = require('path');

const ruta = path.join(os.homedir(), 'Desktop', 'n8n-plantillas', 'lead-sin-fuga', 'lead-sin-fuga.json');
const wf = JSON.parse(fs.readFileSync(ruta, 'utf8'));
const codigo = {};
for (const n of wf.nodes) {
  if (n.type === 'n8n-nodes-base.code') codigo[n.name] = n.parameters.jsCode;
}

const CFG = {
  prefijo_pais: '57', zona_horaria: 'America/Bogota', hora_inicio: '8', hora_fin: '18',
  dias_habiles: '1,2,3,4,5,6', vendedores: 'Ana,Luis', chats_vendedores: '111,222',
  chat_respaldo: '999',
  palabras_intencion: 'precio,cotizacion,cuanto vale,comprar,disponible,domicilio,urgente,agendar,cita',
  umbral_caliente: '55', umbral_tibio: '30',
  promesa_en_horario: 'En 15 minutos.', promesa_fuera_horario: 'Manana temprano.',
};
const CFGS = {
  zona_horaria: 'America/Bogota', hora_inicio: '0', hora_fin: '24', dias_habiles: '0,1,2,3,4,5,6',
  horas_de_espera: '24', intentos_maximos: '3', tope_por_ejecucion: '25',
};

function correr(nombre, entrada, refs) {
  const $json = entrada;
  const $input = { all: () => (Array.isArray(entrada) ? entrada.map(j => ({ json: j })) : [{ json: entrada }]) };
  const $ = (n) => {
    if (!(n in refs)) throw new Error('referencia no simulada: ' + n);
    return { first: () => ({ json: refs[n] }) };
  };
  const fn = new Function('$json', '$input', '$', codigo[nombre]);
  return fn($json, $input, $);
}

let fallos = 0;
const comprobar = (etiqueta, condicion, detalle) => {
  if (condicion) { console.log('  ok   ' + etiqueta); }
  else { console.log('  FALLA ' + etiqueta + (detalle ? '  -> ' + JSON.stringify(detalle) : '')); fallos++; }
};

console.log('\n1. Normalizar y validar');

// Caso tipico: formulario web en espanol, telefono con espacios y guiones.
let r = correr('Normalizar y validar',
  { body: { Nombre: 'Maria Gomez', ['Teléfono']: '320 456-7890', correo: 'MARIA@Ejemplo.com ',
            mensaje: 'Quiero saber el precio y si tienen domicilio en Cucuta' }, headers: {} },
  { Configuracion: CFG })[0].json;
comprobar('telefono movil a E.164', r.telefono === '+573204567890', r.telefono);
comprobar('correo en minusculas y validado', r.email === 'maria@ejemplo.com', r.email);
comprobar('mensaje capturado', r.mensaje.includes('precio'), r.mensaje);
comprobar('lead valido', r.valido === true);
const idMaria = r.lead_id;

// Alias en ingles, mayusculas y guiones bajos.
let r2 = correr('Normalizar y validar',
  { body: { full_name: 'John Doe', PHONE_NUMBER: '+57 300 1112233', Message: 'quote please' }, headers: {} },
  { Configuracion: CFG })[0].json;
comprobar('alias en ingles reconocidos', r2.nombre === 'John Doe' && r2.telefono === '+573001112233', [r2.nombre, r2.telefono]);

// Fijo de Cucuta de 7 digitos.
let r3 = correr('Normalizar y validar',
  { body: { nombre: 'Taller Pena', telefono: '5712345' }, headers: {} },
  { Configuracion: CFG })[0].json;
comprobar('fijo de 7 digitos toma indicativo', r3.telefono === '+5775712345', r3.telefono);

// Correo invalido se descarta pero el telefono salva el lead.
let r4 = correr('Normalizar y validar',
  { body: { nombre: 'X', telefono: '3001234567', email: 'no-es-correo' }, headers: {} },
  { Configuracion: CFG })[0].json;
comprobar('correo invalido se vacia', r4.email === '', r4.email);
comprobar('sigue valido por telefono', r4.valido === true);

// Sin ninguna via de contacto: rechazo.
let r5 = correr('Normalizar y validar',
  { body: { nombre: 'Solo nombre', mensaje: 'hola' }, headers: {} },
  { Configuracion: CFG })[0].json;
comprobar('sin contacto se rechaza', r5.valido === false && r5.lead_id === '', r5);
comprobar('da motivo del rechazo', r5.motivo_rechazo.length > 10, r5.motivo_rechazo);

// Idempotencia: el mismo telefono escrito distinto produce el mismo identificador.
let r6 = correr('Normalizar y validar',
  { body: { nombre: 'Maria G.', telefono: '(320) 4567890', correo: 'otro@correo.com' }, headers: {} },
  { Configuracion: CFG })[0].json;
comprobar('mismo telefono, mismo lead_id', r6.lead_id === idMaria, [idMaria, r6.lead_id]);

// Y dos personas distintas no colisionan.
let r7 = correr('Normalizar y validar',
  { body: { nombre: 'Otra', telefono: '3209999999' }, headers: {} },
  { Configuracion: CFG })[0].json;
comprobar('personas distintas, ids distintos', r7.lead_id !== idMaria);

// Detecta WhatsApp por cabecera.
let r8 = correr('Normalizar y validar',
  { body: { nombre: 'W', telefono: '3001112222' }, headers: { 'user-agent': 'WhatsApp/2.23' } },
  { Configuracion: CFG })[0].json;
comprobar('canal whatsapp por cabecera', r8.canal === 'whatsapp', r8.canal);

// Cuerpo plano, sin envoltorio body.
let r9 = correr('Normalizar y validar',
  { nombre: 'Plano', telefono: '3011112222' },
  { Configuracion: CFG })[0].json;
comprobar('acepta cuerpo sin envoltorio', r9.valido === true && r9.telefono === '+573011112222', r9.telefono);

console.log('\n2. Puntuar y asignar');

let p = correr('Puntuar y asignar', {}, { Configuracion: CFG, 'Normalizar y validar': r })[0].json;
comprobar('puntaje en rango', p.puntaje >= 0 && p.puntaje <= 100, p.puntaje);
comprobar('lead con intencion sale caliente', p.temperatura === 'caliente', [p.puntaje, p.temperatura]);
comprobar('explica el puntaje', p.motivo_puntaje.includes('Pide'), p.motivo_puntaje);
comprobar('asigna vendedor de la lista', ['Ana', 'Luis'].includes(p.vendedor), p.vendedor);
comprobar('asigna chat coherente', (p.vendedor === 'Ana' ? '111' : '222') === p.chat_vendedor, [p.vendedor, p.chat_vendedor]);
comprobar('estado inicial nuevo', p.estado === 'nuevo' && p.intentos_seguimiento === 0);
comprobar('conserva datos del lead', p.telefono === r.telefono && p.lead_id === r.lead_id);

// Reparto estable ante repeticion.
let p2 = correr('Puntuar y asignar', {}, { Configuracion: CFG, 'Normalizar y validar': r })[0].json;
comprobar('el reparto es estable', p2.vendedor === p.vendedor, [p.vendedor, p2.vendedor]);

// Lead frio: sin intencion, sin nombre, canal web.
const frio = Object.assign({}, r, { mensaje: 'hola', interes: '', nombre: 'Sin nombre', email: '', canal: 'web' });
let p3 = correr('Puntuar y asignar', {}, { Configuracion: CFG, 'Normalizar y validar': frio })[0].json;
comprobar('lead sin senales sale frio', p3.temperatura === 'frio', [p3.puntaje, p3.temperatura]);

// Un solo vendedor configurado.
const cfgUno = Object.assign({}, CFG, { vendedores: 'Solo Yo', chats_vendedores: '555' });
let p4 = correr('Puntuar y asignar', {}, { Configuracion: cfgUno, 'Normalizar y validar': r })[0].json;
comprobar('funciona con un solo vendedor', p4.vendedor === 'Solo Yo' && p4.chat_vendedor === '555', [p4.vendedor, p4.chat_vendedor]);

// Sin vendedores configurados no debe romper.
const cfgCero = Object.assign({}, CFG, { vendedores: '', chats_vendedores: '' });
let p5 = correr('Puntuar y asignar', {}, { Configuracion: cfgCero, 'Normalizar y validar': r })[0].json;
comprobar('sin vendedores no rompe', p5.vendedor === 'Sin asignar' && p5.chat_vendedor === '999', [p5.vendedor, p5.chat_vendedor]);

// Horario: la promesa cambia, el puntaje no se hunde.
const domingo = Object.assign({}, r, { dia_semana: 0, hora_local: 23 });
let p6 = correr('Puntuar y asignar', {}, { Configuracion: CFG, 'Normalizar y validar': domingo })[0].json;
comprobar('fuera de horario cambia la promesa', p6.en_horario === false && p6.promesa === CFG.promesa_fuera_horario, p6.promesa);

console.log('\n3. Filtrar los que exigen seguimiento');

const hace = (h) => new Date(Date.now() - h * 3600e3).toISOString();
const filas = [
  { lead_id: 'aaa', nombre: 'Viejo caliente', estado: 'nuevo', intentos_seguimiento: 0, fecha_alta: hace(30), ultimo_contacto: '', puntaje: 80 },
  { lead_id: 'bbb', nombre: 'Recien llegado', estado: 'nuevo', intentos_seguimiento: 0, fecha_alta: hace(2), ultimo_contacto: '', puntaje: 90 },
  { lead_id: 'ccc', nombre: 'Ya atendido', estado: 'contactado', intentos_seguimiento: 0, fecha_alta: hace(50), ultimo_contacto: '', puntaje: 70 },
  { lead_id: 'ddd', nombre: 'Agotado', estado: 'nuevo', intentos_seguimiento: 3, fecha_alta: hace(200), ultimo_contacto: hace(100), puntaje: 60 },
  { lead_id: 'eee', nombre: 'Segundo intento', estado: 'nuevo', intentos_seguimiento: 1, fecha_alta: hace(80), ultimo_contacto: hace(50), puntaje: 40 },
  { lead_id: 'fff', nombre: 'Espera no cumplida', estado: 'nuevo', intentos_seguimiento: 1, fecha_alta: hace(60), ultimo_contacto: hace(30), puntaje: 95 },
  { lead_id: '', nombre: 'Fila vacia de la hoja', estado: '', intentos_seguimiento: 0, fecha_alta: '', ultimo_contacto: '' },
  { lead_id: 'ggg', nombre: 'Fecha corrupta', estado: 'nuevo', intentos_seguimiento: 0, fecha_alta: 'no-es-fecha', ultimo_contacto: '', puntaje: 50 },
];
let f = correr('Filtrar los que exigen seguimiento', filas, { 'Configuracion del seguimiento': CFGS });
const ids = f.map(x => x.json.lead_id);
comprobar('selecciona solo a quien toca', JSON.stringify(ids) === JSON.stringify(['aaa', 'eee']), ids);
comprobar('salta al recien llegado', !ids.includes('bbb'));
comprobar('salta al ya atendido', !ids.includes('ccc'));
comprobar('salta al que agoto intentos', !ids.includes('ddd'));
comprobar('respeta la espera creciente', !ids.includes('fff'));
comprobar('ignora filas vacias y fechas corruptas', !ids.includes('') && !ids.includes('ggg'));
comprobar('cuenta el intento', f[0].json.intento === 1 && f[1].json.intento === 2, f.map(x => x.json.intento));
comprobar('calcula restantes', f[1].json.intentos_restantes === 1, f[1].json.intentos_restantes);
comprobar('ordena por puntaje', f[0].json.puntaje >= f[1].json.puntaje);

// Fuera de horario no se avisa a nadie.
const fueraDeHorario = Object.assign({}, CFGS, { hora_inicio: '8', hora_fin: '8' });
let f2 = correr('Filtrar los que exigen seguimiento', filas, { 'Configuracion del seguimiento': fueraDeHorario });
comprobar('fuera de horario no avisa', f2.length === 0, f2.length);

// Hoja vacia.
let f3 = correr('Filtrar los que exigen seguimiento', [], { 'Configuracion del seguimiento': CFGS });
comprobar('hoja vacia no rompe', Array.isArray(f3) && f3.length === 0);

// Tope por ejecucion.
const muchos = Array.from({ length: 60 }, (_, i) => ({
  lead_id: 'x' + i, estado: 'nuevo', intentos_seguimiento: 0, fecha_alta: hace(40), ultimo_contacto: '', puntaje: i,
}));
let f4 = correr('Filtrar los que exigen seguimiento', muchos, { 'Configuracion del seguimiento': CFGS });
comprobar('respeta el tope por ejecucion', f4.length === 25, f4.length);

console.log(fallos === 0 ? '\nTODAS LAS PRUEBAS PASAN\n' : '\n' + fallos + ' FALLOS\n');
process.exit(fallos ? 1 : 0);
