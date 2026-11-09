<#
.SYNOPSIS
    Crea un proyecto con el terreno de un caso de referencia y le genera una alternativa por la API.

.DESCRIPTION
    Con el stack de desarrollo levantado (docker compose up -d), desde la raiz del repo:

        $env:TRAZADOS_EMAIL = 'director@estudio.com.ar'
        $env:TRAZADOS_CONTRASENA = '<la contrasena>'      # o se la pide al arrancar
        powershell -ExecutionPolicy Bypass -File scripts\generar-referencia.ps1

    1. Verifica /api/health e inicia sesion (D63) con un usuario que pueda registrar proyectos y
       generar: el director tecnico (p. 54). La contrasena no se pasa como argumento, para que no
       quede en el historial de la consola.
    2. Pide los cuerpos JSON al contenedor api (tests/datos_referencia.py, copia unica del caso
       de referencia del motor) y los manda tal cual, sin rearmar coordenadas en PowerShell.
    3. Busca el cliente de referencia (por razon social) o lo da de alta (POST /api/clientes):
       el proyecto lo exige (CU03).
    4. Crea el proyecto (POST /api/proyectos) y genera la alternativa
       (POST /api/proyectos/{id}/alternativas).
    5. Muestra los indicadores y los incumplimientos, y guarda cada capa como .geojson para
       abrirla en QGIS (EPSG:4326).

    El script es solo ASCII a proposito: PowerShell 5.1 lee un .ps1 sin BOM como ANSI y rompe
    los acentos. Los acentos que vienen de la API se decodifican como UTF-8.

.PARAMETER Url
    Entrada de Nginx. Por defecto, la de desarrollo.

.PARAMETER Email
    Correo con el que se inicia sesion. Por defecto, $env:TRAZADOS_EMAIL. La contrasena sale de
    $env:TRAZADOS_CONTRASENA o se pide por consola, sin mostrarla.

.PARAMETER Caso
    Terreno del proyecto, uno de motor_trazados.referencia.CASOS: referencia (el rectangular,
    por defecto), irregular, l, u o triangulo (D40), o uno con areas reservadas (D59):
    reservada_centro (el rectangular con un area de 120 x 50 m en el medio, alineada con la
    grilla) y reservada_borde (el irregular con una franja de servidumbre de 20 m contra su lado
    oblicuo, como la de la p. 48). Ademas, el caso de demostracion prototipo (tests/datos_referencia.py,
    DEMOS; D73): el pentagono de los prototipos de las p. 48 a 51, con la servidumbre de electroducto
    sobre el borde este, A1 desde la calle publica (20 m) y A2 desde el camino vecinal (14 m). El
    codigo del proyecto empieza con las tres primeras letras del caso.

.PARAMETER IdProyecto
    Si se indica, no crea un proyecto: genera otra alternativa del proyecto existente.

.PARAMETER SoloProyecto
    Crea el proyecto y no genera: para abrirlo en el portal y generar desde ahi.

.PARAMETER Orientacion
    Orientacion de la grilla en grados (por defecto, la del caso de referencia: 20).

.PARAMETER Semilla
    Semilla de la estrategia (por defecto, la del caso de referencia: 1042).

.PARAMETER Criterio
    Criterio del asignador de espacios verdes (D46, D51): cercania (el de referencia desde el
    motor 0.7.0) o menos_lotes. Si el proyecto no lo tiene, configura antes de generar una version
    nueva de los parametros (CU05) con los valores de referencia y ese criterio. Sin -Criterio se
    genera con el vigente.

.PARAMETER SinAvenidas
    Antes de generar, configura una version nueva de los parametros (CU05) con los valores de
    referencia y sin el 20 % de avenidas de la Ley 4146, art. 12: todas las calles son la local
    de 12 m (la casilla "Exigir avenidas" desmarcada, D85). Se combina con -Criterio.

.PARAMETER CalleBorde
    Por donde va la calle de borde (D50, D86): por_lado (el de referencia desde el motor 0.11.0) o
    contorno (la casilla "Calle de borde en todo el contorno" marcada, como hasta el motor 0.10.x).
    Si el proyecto no la tiene, configura antes de generar una version nueva de los parametros
    (CU05). Se combina con -Criterio y -SinAvenidas.

.PARAMETER Comparacion
    Crea un proyecto con tres alternativas bien distintas para la comparacion (CU13, D54) y
    muestra la tabla de las tres. El caso es irregular salvo que se pase -Caso: en el rectangular
    los dos criterios del verde dan los mismos lotes. Las tres alternativas son:
      A: la orientacion sugerida, con el criterio del verde "mas cercania" (cercania);
      B: la misma estrategia, con "menos lotes perdidos" (parametros v2, CU05);
      C: otra orientacion (la sugerida + 90 grados, o -OtraOrientacion), con "mas cercania"
         (parametros v3).
    Cada par desde A aisla una decision: el criterio (A-B) o la orientacion (A-C).

.PARAMETER OtraOrientacion
    Con -Comparacion, la orientacion de la alternativa C en grados.

.PARAMETER Recalculo
    Demo de fijar sectores y recalcular (CU09, D56): crea el proyecto del caso (el rectangular
    salvo que se pase -Caso), genera A con la estrategia de referencia, pide la vista previa del
    sector de -Manzanas (POST /api/versiones/{id}/sector), recalcula el resto con la estrategia
    que sugiere la API (la de la v1, D60; o -Orientacion) y muestra lo fijado, los anclajes unidos,
    los empalmes y las diferencias con la v1. Con un caso con areas, el recalculo usa las de la v1.
    Guarda las capas de la v2 y escribe las direcciones del portal (la v2 y la comparacion v1/v2).

.PARAMETER Manzanas
    Con -Recalculo, las manzanas que se fijan (por defecto M6 y M7, las de la p. 50).

.PARAMETER Compartir
    Despues de generar, comparte la alternativa con el cliente (CU14, D70): la selecciona
    (PATCH /api/proyectos/{id}/seleccion), genera un enlace que vence en -Dias dias
    (POST /api/proyectos/{id}/enlaces) e imprime la direccion del cliente, con el token en el
    fragmento (#/compartido/<token>, D71). El token se muestra esa unica vez: la base guarda su hash.
    Abrila en una ventana privada: el cliente no tiene cuenta (CU15).

.PARAMETER Dias
    Con -Compartir, en cuantos dias vence el enlace (de 0 a 30; por defecto 7). Lo valida la API.

.PARAMETER Salida
    Carpeta donde se guardan las capas. Por defecto, salida\api\ en la raiz del repo (ignorada
    por git).
#>
param(
    [string]$Url = 'http://localhost:8080',
    [string]$Email = $env:TRAZADOS_EMAIL,
    [ValidateSet('referencia', 'irregular', 'l', 'u', 'triangulo', 'reservada_centro', 'reservada_borde', 'prototipo')]
    [string]$Caso = 'referencia',
    [int]$IdProyecto = 0,
    [switch]$SoloProyecto,
    [Nullable[double]]$Orientacion = $null,
    [Nullable[int]]$Semilla = $null,
    [ValidateSet('', 'menos_lotes', 'cercania')]
    [string]$Criterio = '',
    [switch]$SinAvenidas,
    [ValidateSet('', 'contorno', 'por_lado')]
    [string]$CalleBorde = '',
    [switch]$Comparacion,
    [Nullable[double]]$OtraOrientacion = $null,
    [switch]$Recalculo,
    [string[]]$Manzanas = @('M6', 'M7'),
    [switch]$Compartir,
    [int]$Dias = 7,
    [string]$Salida = ''
)

$ErrorActionPreference = 'Stop'
if ($Compartir -and ($Recalculo -or $Comparacion -or $SoloProyecto)) {
    throw '-Compartir comparte la alternativa que genera: no se combina con -Recalculo, -Comparacion ni -SoloProyecto.'
}
if ($Recalculo -and ($Comparacion -or $IdProyecto -gt 0 -or $SoloProyecto -or $Criterio -or $SinAvenidas -or $CalleBorde)) {
    throw '-Recalculo crea su propio proyecto: no se combina con -Comparacion, -IdProyecto, -SoloProyecto, -Criterio, -SinAvenidas ni -CalleBorde.'
}
if ($Comparacion) {
    if ($IdProyecto -gt 0 -or $SoloProyecto -or $Criterio -or $SinAvenidas -or $CalleBorde -or $null -ne $Orientacion -or $null -ne $Semilla) {
        throw '-Comparacion crea su propio proyecto con sus tres estrategias: no se combina con -IdProyecto, -SoloProyecto, -Criterio, -SinAvenidas, -CalleBorde, -Orientacion ni -Semilla.'
    }
    if (-not $PSBoundParameters.ContainsKey('Caso')) { $Caso = 'irregular' }
} elseif ($null -ne $OtraOrientacion) {
    throw '-OtraOrientacion va con -Comparacion.'
}
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
if (-not $Salida) { $Salida = Join-Path $raiz 'salida\api' }
$invariante = [Globalization.CultureInfo]::InvariantCulture

Add-Type -AssemblyName System.Net.Http
$http = New-Object System.Net.Http.HttpClient
$http.Timeout = [TimeSpan]::FromMinutes(3)

function Llamar([string]$Metodo, [string]$Ruta, [string]$Json = $null) {
    # HttpClient y no Invoke-WebRequest: en PowerShell 5.1 este decodifica la respuesta como
    # ISO-8859-1 (la API no manda charset) y lanza excepcion ante un 4xx.
    $pedido = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Metodo), $Url + $Ruta)
    if ($Json) {
        $pedido.Content = New-Object System.Net.Http.StringContent($Json, [Text.Encoding]::UTF8, 'application/json')
    }
    $respuesta = $http.SendAsync($pedido).GetAwaiter().GetResult()
    $bytes = $respuesta.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
    $texto = [Text.Encoding]::UTF8.GetString($bytes)
    $datos = $null
    if ($texto) { $datos = $texto | ConvertFrom-Json }
    [pscustomobject]@{ Estado = [int]$respuesta.StatusCode; Texto = $texto; Datos = $datos }
}

function Fallar([string]$Paso, $Respuesta) {
    Write-Host ''
    Write-Host "Fallo $Paso (HTTP $($Respuesta.Estado))" -ForegroundColor Red
    $error_ = $Respuesta.Datos
    if ($error_ -and $error_.causa) {
        Write-Host "  Causa:      $($error_.causa)"
        if ($error_.sugerencia) { Write-Host "  Sugerencia: $($error_.sugerencia)" }
        foreach ($p in $error_.problemas) { Write-Host "  - $($p.campo): $($p.mensaje)" }
    } else {
        Write-Host $Respuesta.Texto
    }
    exit 1
}

function Cuerpo([string[]]$Argumentos) {
    # Los cuerpos los arma Python dentro del contenedor (JSON en ASCII).
    $salida = & docker compose exec -T api python -m tests.datos_referencia @Argumentos
    if ($LASTEXITCODE -ne 0) { throw "No se pudo armar el cuerpo ($($Argumentos -join ' '))." }
    return ($salida -join "`n")
}

function Guardar([string]$Ruta, [string]$Texto) {
    # UTF-8 sin BOM, que es lo que espera un lector de GeoJSON.
    [IO.File]::WriteAllText($Ruta, $Texto, (New-Object System.Text.UTF8Encoding $false))
}

# --- 1. La API tiene que estar sana -----------------------------------------------------------
$salud = Llamar 'GET' '/api/health'
if ($salud.Estado -ne 200) { Fallar 'el chequeo de /api/health' $salud }
Write-Host "API operativa: PostGIS $($salud.Datos.postgis), motor $($salud.Datos.motor)"

# --- 1 bis. Inicio de sesion (D63): la cookie la guarda el HttpClient y va en cada pedido ---------
if (-not $Email) { throw 'Falta el correo: -Email o $env:TRAZADOS_EMAIL.' }
$contrasena = $env:TRAZADOS_CONTRASENA
if (-not $contrasena) {
    $segura = Read-Host -AsSecureString "Contrasena de $Email"
    $contrasena = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura))
}
$credenciales = @{ email = $Email; contrasena = $contrasena } | ConvertTo-Json -Compress
$sesion = Llamar 'POST' '/api/sesion' $credenciales
$credenciales = $null
$contrasena = $null
if ($sesion.Estado -ne 200) { Fallar 'el inicio de sesion' $sesion }
if ($sesion.Datos.debe_cambiar_contrasena) {
    throw "$Email tiene una contrasena temporal: cambiala en el portal antes de usar el script."
}
Write-Host "Sesion de $($sesion.Datos.usuario.nombre) $($sesion.Datos.usuario.apellido) ($($sesion.Datos.usuario.rol))"

# --- 2. Proyecto, con su cliente ---------------------------------------------------------------
if ($IdProyecto -gt 0) {
    $proyecto = Llamar 'GET' "/api/proyectos/$IdProyecto"
    if ($proyecto.Estado -ne 200) { Fallar "la lectura del proyecto $IdProyecto" $proyecto }
} else {
    $cuerpoCliente = Cuerpo @('cliente')
    $razonSocial = ($cuerpoCliente | ConvertFrom-Json).razon_social
    $clientes = Llamar 'GET' '/api/clientes'
    if ($clientes.Estado -ne 200) { Fallar 'la lista de clientes' $clientes }
    $clienteRef = @($clientes.Datos | Where-Object { $_.razon_social -eq $razonSocial }) | Select-Object -First 1
    if (-not $clienteRef) {
        $alta = Llamar 'POST' '/api/clientes' $cuerpoCliente
        if ($alta.Estado -ne 201) { Fallar 'el alta del cliente' $alta }
        $clienteRef = $alta.Datos
    }
    $prefijo = $Caso.Substring(0, [Math]::Min(3, $Caso.Length)).ToUpperInvariant()
    $codigo = $prefijo + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    $proyecto = Llamar 'POST' '/api/proyectos' (Cuerpo @('proyecto', $codigo, [string]$clienteRef.id_cliente, $Caso))
    if ($proyecto.Estado -ne 201) { Fallar 'el alta del proyecto' $proyecto }
}
$p = $proyecto.Datos
Write-Host ("Proyecto {0} (id {1}) de {2}, sistema de calculo EPSG:{3}, terreno de {4:N2} m2" -f `
    $p.codigo, $p.id_proyecto, $p.cliente.razon_social, $p.srid_calculo, $p.terreno.properties.superficie_m2)
function Configurar([string]$CriterioPedido, [bool]$SinAvenidasPedido = $false, [string]$CalleBordePedida = '') {
    # CU05: una version nueva del conjunto, con los valores de referencia y el criterio pedido. Sin
    # avenidas, el porcentaje del art. 12 en 0 (la casilla "Exigir avenidas" desmarcada, D85). Con
    # $CalleBordePedida, esa calle de borde (D86); si no, la de referencia.
    $referencia = Llamar 'GET' '/api/parametros/referencia'
    if ($referencia.Estado -ne 200) { Fallar 'la lectura de los valores de referencia' $referencia }
    $valores = $referencia.Datos.valores
    $valores.loteo.criterio_espacio_verde = $CriterioPedido
    if ($SinAvenidasPedido) { $valores.loteo.porcentaje_minimo_avenidas = 0 }
    if ($CalleBordePedida) { $valores.loteo.calle_borde = $CalleBordePedida }
    $configurado = Llamar 'POST' "/api/proyectos/$($p.id_proyecto)/parametros" ($valores | ConvertTo-Json -Depth 16 -Compress)
    if ($configurado.Estado -ne 201) { Fallar 'la configuracion de los parametros' $configurado }
    $sinAvenidasTexto = if ($SinAvenidasPedido) { ', sin avenidas (D85)' } else { '' }
    Write-Host ("Parametros v$($configurado.Datos.version) con el criterio del espacio verde $CriterioPedido$sinAvenidasTexto" +
        " y la calle de borde $($configurado.Datos.loteo.calle_borde) (CU05)")
}

function Generar([string[]]$Argumentos) {
    # CU06: genera, muestra los indicadores y guarda las capas para QGIS. Devuelve la alternativa.
    $generada = Llamar 'POST' "/api/proyectos/$($p.id_proyecto)/alternativas" (Cuerpo $Argumentos)
    if ($generada.Estado -ne 201) { Fallar 'la generacion de la alternativa' $generada }
    $a = $generada.Datos
    $v = $a.version
    $i = $v.indicadores

    Write-Host ''
    Write-Host ("Alternativa {0} (id {1}), version {2} (id {3}), generada en {4} ms con el motor {5}" -f `
        $a.codigo, $a.id_alternativa, $v.numero, $v.id_version, $v.duracion_ms, $v.version_motor)
    Write-Host ("Estrategia: {0}, {1} grados, semilla {2}; parametros v{3}" -f `
        $v.estrategia.patron_red, $v.estrategia.orientacion_grados, $v.estrategia.semilla, $v.version_parametros)
    Write-Host ''
    Write-Host 'Indicadores'
    Write-Host ("  Celdas utiles:             {0}" -f $i.cantidad_celdas)
    Write-Host ("  Superficie aprovechable:   {0:N2} m2" -f $i.superficie_aprovechable_m2)
    Write-Host ("  Circulacion:               {0:N2} %" -f $i.porcentaje_circulacion)
    # La base de los porcentajes la dice la API (D61): la superficie disponible, o el terreno en una version anterior.
    $base = if ($i.base_porcentajes -eq 'disponible') { 'de la superficie disponible' } else { 'del terreno' }
    Write-Host ("  Espacio verde:             {0:N2} m2 ({1:N2} % {2})" -f $i.superficie_espacio_verde_m2, $i.porcentaje_espacio_verde, $base)
    Write-Host ("  Espacio libre:             {0:N2} m2" -f $i.superficie_espacio_libre_m2)
    Write-Host ("  Cesion alcanzada:          {0:N2} % de la superficie de lotes" -f $i.porcentaje_cesion)
    Write-Host ("  Avenidas:                  {0:N2} % de la longitud de la red" -f $i.porcentaje_avenidas)
    Write-Host ("  Lotes grandes:             {0}" -f $i.cantidad_lotes_grandes)
    Write-Host ("  Distancia al verde:        media {0:N2} m, maxima {1:N2} m" -f $i.distancia_media_verde_m, $i.distancia_maxima_verde_m)
    $celdas = @($v.capas.celdas.features) | Group-Object { $_.properties.tipo }
    Write-Host ("  Celdas por tipo:           {0}" -f (($celdas | ForEach-Object { "$($_.Name) $($_.Count)" }) -join ', '))
    Write-Host ("  Longitud de red:           {0:N2} m" -f $i.longitud_red_m)
    Write-Host ("  Distancia media al acceso: {0:N2} m" -f $i.distancia_media_acceso_m)
    $areas = @($v.capas.areas_reservadas.features)
    Write-Host ("  Areas reservadas:          {0} ({1:N2} m2)" -f $areas.Count, $i.superficie_reservada_m2)
    Write-Host ''
    $incumplimientos = @($v.capas.incumplimientos.features)
    if ($v.cumple_restricciones) {
        Write-Host 'Cumple todas las restricciones.' -ForegroundColor Green
    } else {
        Write-Host "No cumple: $($incumplimientos.Count) incumplimiento(s)" -ForegroundColor Yellow
        $incumplimientos | Group-Object { $_.properties.tipo } | ForEach-Object {
            Write-Host ("  {0}: {1}" -f $_.Name, $_.Count)
        }
        $incumplimientos | Select-Object -First 3 | ForEach-Object {
            Write-Host ("  - {0}: {1}" -f $_.properties.elemento, $_.properties.detalle)
        }
    }

    # Capas para QGIS.
    $carpeta = Join-Path $Salida ("{0}-{1}" -f $p.codigo, $a.codigo)
    New-Item -ItemType Directory -Force $carpeta | Out-Null
    Guardar (Join-Path $carpeta 'alternativa.json') $generada.Texto
    $terreno = [pscustomobject]@{ type = 'FeatureCollection'; features = @($p.terreno) }
    Guardar (Join-Path $carpeta 'terreno.geojson') ($terreno | ConvertTo-Json -Depth 32 -Compress)
    Guardar (Join-Path $carpeta 'accesos.geojson') ($p.accesos | ConvertTo-Json -Depth 32 -Compress)
    foreach ($capa in $v.capas.PSObject.Properties) {
        Guardar (Join-Path $carpeta "$($capa.Name).geojson") ($capa.Value | ConvertTo-Json -Depth 32 -Compress)
    }
    Write-Host ''
    Write-Host "Capas guardadas en $carpeta"
    Write-Host "Alternativa en la API: $Url/api/alternativas/$($a.id_alternativa)"
    Write-Host "En el portal: $Url/#/proyectos/$($p.id_proyecto)/$($a.codigo)"
    return $a
}

function Numero($Valor) {
    if ($null -eq $Valor) { return '-' }
    return ([double]$Valor).ToString('N2')
}

if ($Comparacion) {
    # --- 3. Tres alternativas para la comparacion (CU13, D54) ----------------------------------
    $sugerida = $p.estrategia_sugerida
    $o = [double]$sugerida.orientacion_grados
    $s = [int]$sugerida.semilla
    $otra = if ($null -ne $OtraOrientacion) { [double]$OtraOrientacion } else { ($o + 90) % 180 }
    $estrategia = @('generacion', $o.ToString($invariante), $s.ToString($invariante))
    if ($p.parametros.loteo.criterio_espacio_verde -ne 'cercania') { Configurar 'cercania' }
    $altA = Generar $estrategia
    Configurar 'menos_lotes'
    $altB = Generar $estrategia
    Configurar 'cercania'
    $altC = Generar @('generacion', $otra.ToString($invariante), $s.ToString($invariante))

    $ids = @($altA, $altB, $altC) | ForEach-Object { "alternativas=$($_.id_alternativa)" }
    $comparada = Llamar 'GET' ("/api/proyectos/$($p.id_proyecto)/comparacion?" + ($ids -join '&'))
    if ($comparada.Estado -ne 200) { Fallar 'la comparacion' $comparada }
    $c = $comparada.Datos
    Write-Host ''
    Write-Host 'Comparacion (CU13): A, B y C, la diferencia contra A y el mejor (solo donde la direccion es clara)'
    foreach ($fila in $c.indicadores) {
        $mejores = (@($fila.mejores) | ForEach-Object { $c.alternativas[$_].codigo }) -join ', '
        if (-not $mejores) { $mejores = if ($fila.sentido) { 'empate' } else { 'disyuntiva' } }
        Write-Host ("  {0,-28} {1,12} {2,12} {3,12}   B-A {4,10}  C-A {5,10}   {6}" -f $fila.indicador, `
            (Numero $fila.valores[0]), (Numero $fila.valores[1]), (Numero $fila.valores[2]), `
            (Numero $fila.diferencias[1]), (Numero $fila.diferencias[2]), $mejores)
    }
    Write-Host 'Lo que difiere:'
    foreach ($d in $c.diferencias) { Write-Host ("  {0}: {1}" -f $d.campo, (@($d.valores) -join ' | ')) }
    Write-Host ''
    Write-Host 'En el portal, de a pares y las tres:'
    foreach ($par in @('A/B', 'A/C', 'B/C', 'A/B/C')) {
        Write-Host "  $Url/#/proyectos/$($p.id_proyecto)/comparar/$par"
    }
    exit 0
}

if ($Recalculo) {
    # --- 3. Fijar sectores y recalcular (CU09, D56) --------------------------------------------
    $altA = Generar @('generacion')
    $v1 = $altA.version

    # Paso 3 del CU09: lo que se conservaria, sin guardar nada, con la estrategia sugerida (D60).
    $sector = Llamar 'POST' "/api/versiones/$($v1.id_version)/sector" (@{ manzanas = @($Manzanas) } | ConvertTo-Json -Compress)
    if ($sector.Estado -ne 200) { Fallar 'la vista previa del sector' $sector }
    $vs = $sector.Datos
    $sugerida = $vs.estrategia_sugerida
    $s = if ($null -ne $Semilla) { [int]$Semilla } else { [int]$sugerida.semilla }
    $o = if ($null -ne $Orientacion) { [double]$Orientacion } else { [double]$sugerida.orientacion_grados }
    Write-Host ("Estrategia sugerida para recalcular: {0} grados, semilla {1} (la de la v{2})" -f `
        $sugerida.orientacion_grados, $sugerida.semilla, $v1.numero)
    Write-Host ''
    Write-Host ("Sector a fijar de la v{0}: {1}" -f $v1.numero, (@($vs.manzanas) -join ', '))
    Write-Host ("  {0} celdas ({1} lotes, {2} utiles), {3:N2} m2 ({4:N2} % de la superficie disponible), {5} anclajes" -f `
        $vs.cantidad_celdas, $vs.cantidad_lotes, $vs.cantidad_celdas_utiles, $vs.superficie_m2, $vs.porcentaje_disponible, $vs.cantidad_anclajes)

    # Paso 4: confirmar con otra orientacion.
    $argumentos = @('recalculo', $o.ToString($invariante), $s.ToString($invariante)) + @($vs.manzanas)
    $recalculada = Llamar 'POST' "/api/versiones/$($v1.id_version)/recalculos" (Cuerpo $argumentos)
    if ($recalculada.Estado -ne 201) { Fallar 'el recalculo' $recalculada }
    $a = $recalculada.Datos
    $v = $a.version
    $f = $v.fijacion
    Write-Host ''
    Write-Host ("Alternativa {0}, version {1} (id {2}) desde la v{3}, recalculada en {4} ms con el motor {5}" -f `
        $a.codigo, $v.numero, $v.id_version, $f.numero_origen, $v.duracion_ms, $v.version_motor)
    Write-Host ("Estrategia: {0}, {1} grados, semilla {2}; parametros v{3}" -f `
        $v.estrategia.patron_red, $v.estrategia.orientacion_grados, $v.estrategia.semilla, $v.version_parametros)
    Write-Host ("Sector fijado: {0}; {1} celdas ({2} lotes), {3:N2} m2" -f `
        (@($f.manzanas) -join ', '), $f.cantidad_celdas, $f.cantidad_lotes, $f.superficie_m2)
    Write-Host ("Anclajes unidos a la red nueva: {0} de {1}; empalmes sobre calles fijadas: {2}" -f `
        $f.cantidad_anclajes_unidos, $f.cantidad_anclajes, $f.cantidad_empalmes)
    if ($v.cumple_restricciones) {
        Write-Host 'Cumple todas las restricciones.' -ForegroundColor Green
    } else {
        $incumplimientos = @($v.capas.incumplimientos.features)
        Write-Host "No cumple: $($incumplimientos.Count) incumplimiento(s)" -ForegroundColor Yellow
        $incumplimientos | Select-Object -First 3 | ForEach-Object {
            Write-Host ("  - {0}: {1}" -f $_.properties.elemento, $_.properties.detalle)
        }
    }
    Write-Host ''
    Write-Host ("Diferencias entre versiones (p. 50): v{0}, v{1} y la diferencia" -f $f.numero_origen, $v.numero)
    foreach ($fila in $v.diferencias_con_origen) {
        Write-Host ("  {0,-32} {1,12} {2,12} {3,12}" -f $fila.indicador, (Numero $fila.origen), (Numero $fila.nueva), (Numero $fila.diferencia))
    }

    $carpeta = Join-Path $Salida ("{0}-{1}-v{2}" -f $p.codigo, $a.codigo, $v.numero)
    New-Item -ItemType Directory -Force $carpeta | Out-Null
    Guardar (Join-Path $carpeta 'alternativa.json') $recalculada.Texto
    foreach ($capa in $v.capas.PSObject.Properties) {
        Guardar (Join-Path $carpeta "$($capa.Name).geojson") ($capa.Value | ConvertTo-Json -Depth 32 -Compress)
    }
    Guardar (Join-Path $carpeta 'sector.geojson') ($f.sector | ConvertTo-Json -Depth 32 -Compress)
    Write-Host ''
    Write-Host "Capas de la v$($v.numero) en $carpeta"
    Write-Host "En el portal:"
    Write-Host "  la v$($v.numero):      $Url/#/proyectos/$($p.id_proyecto)/$($a.codigo)/$($v.numero)"
    Write-Host "  la v$($f.numero_origen), para fijar: $Url/#/proyectos/$($p.id_proyecto)/$($a.codigo)/$($f.numero_origen)"
    Write-Host "  v$($f.numero_origen) contra v$($v.numero):  $Url/#/proyectos/$($p.id_proyecto)/comparar/$($a.codigo).$($f.numero_origen)/$($a.codigo).$($v.numero)"
    exit 0
}

$yaSinAvenidas = $p.parametros.loteo.porcentaje_minimo_avenidas -eq 0
$otraCalleBorde = $CalleBorde -and $p.parametros.loteo.calle_borde -ne $CalleBorde
if (($Criterio -and $p.parametros.loteo.criterio_espacio_verde -ne $Criterio) -or ($SinAvenidas -and -not $yaSinAvenidas) -or $otraCalleBorde) {
    $criterioPedido = if ($Criterio) { $Criterio } else { $p.parametros.loteo.criterio_espacio_verde }
    # La calle de borde pedida, o la que ya tiene el proyecto (D86).
    $calleBordePedida = if ($CalleBorde) { $CalleBorde } else { [string]$p.parametros.loteo.calle_borde }
    Configurar $criterioPedido ($SinAvenidas.IsPresent -or $yaSinAvenidas) $calleBordePedida
}
if ($SoloProyecto) {
    Write-Host "Sin generar (-SoloProyecto). En el portal: $Url/#/proyectos/$($p.id_proyecto)"
    exit 0
}

# --- 3. Alternativa ---------------------------------------------------------------------------
$argumentos = @('generacion')
if ($null -ne $Orientacion -or $null -ne $Semilla) {
    $o = if ($null -ne $Orientacion) { $Orientacion } else { 20 }
    $s = if ($null -ne $Semilla) { $Semilla } else { 1042 }
    $argumentos += @(([double]$o).ToString($invariante), ([int]$s).ToString($invariante))
}
$alternativa = Generar $argumentos

if ($Compartir) {
    # CU14 (p. 45, pasos 2 y 10): la seleccion y el enlace. La fecha es la de Cordoba (UTC-3).
    $seleccion = Llamar 'PATCH' "/api/proyectos/$($p.id_proyecto)/seleccion" ('{"alternativas":["' + $alternativa.codigo + '"]}')
    if ($seleccion.Estado -ne 200) { Fallar 'la seleccion de la alternativa' $seleccion }
    $fecha = [DateTime]::UtcNow.AddHours(-3).AddDays($Dias).ToString('yyyy-MM-dd', $invariante)
    $enlace = Llamar 'POST' "/api/proyectos/$($p.id_proyecto)/enlaces" ('{"fecha_vencimiento":"' + $fecha + '"}')
    if ($enlace.Estado -ne 201) { Fallar 'el enlace compartido' $enlace }
    Write-Host ''
    Write-Host ("Enlace para el cliente: comparte {0} v{1} y vence el {2} (se muestra esta unica vez)" -f `
        $alternativa.codigo, $alternativa.version.numero, $fecha) -ForegroundColor Green
    Write-Host "  $Url/#/compartido/$($enlace.Datos.token)"
    Write-Host "Abrilo en una ventana privada: el cliente no tiene cuenta (CU15)."
    Write-Host "Los enlaces del proyecto (y Revocar): $Url/#/proyectos/$($p.id_proyecto)/compartir"
}
