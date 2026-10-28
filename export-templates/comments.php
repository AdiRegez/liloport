<?php
// Liloport – Kommentare für eine exportierte Seite.
// Speichert Kommentare in comments.json im selben Ordner. Kein Login, kein Tracking:
// Name ist freiwillig, gespeichert werden nur Name, Text, Zeit und eine zufällige ID.
// Schutz: Längenlimit, einfache Frequenzbremse pro Herkunft (gehasht, nicht gespeichert), Honeypot-Feld.

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Robots-Tag: noindex');

$datei = __DIR__ . '/comments.json';
$sperre = __DIR__ . '/comments.lock';

// Whitelist-Filter: nur harmlose Tags und Attribute bleiben (Kommentare kommen von anonymen Besuchern).
$ERLAUBT = [
    'p' => [], 'br' => [], 'h2' => [], 'h3' => [], 'h4' => [], 'strong' => [], 'em' => [], 'u' => [], 's' => [], 'sub' => [], 'sup' => [],
    'ul' => [], 'ol' => [], 'li' => [], 'blockquote' => [], 'code' => [], 'pre' => [], 'hr' => [], 'span' => ['style'], 'div' => ['style'],
    'a' => ['href', 'title'], 'img' => ['src', 'alt', 'width', 'height'],
    'table' => [], 'thead' => [], 'tbody' => [], 'tr' => [], 'th' => [], 'td' => [],
];
$UMBENENNEN = ['b' => 'strong', 'i' => 'em', 'strike' => 's'];

function attr_ok($name, $wert) {
    $w = strtolower(trim($wert));
    if ($name === 'href') return preg_match('#^(https?:|mailto:|\#|/|\./|\.\./)#', $w) || strpos($w, ':') === false;
    if ($name === 'src') return (bool)preg_match('#^(https?://|\./|\.\./|assets/)#', $w);
    if ($name === 'style') {
        foreach (explode(';', $w) as $d) {
            $d = trim($d);
            if ($d === '') continue;
            $eig = trim(explode(':', $d, 2)[0]);
            if (!in_array($eig, ['color', 'background-color', 'text-align']) || strpos($d, 'url') !== false) return false;
        }
    }
    return true;
}

function knoten_kopieren($quelle, $ziel, $doc) {
    global $ERLAUBT, $UMBENENNEN;
    foreach ($quelle->childNodes as $k) {
        if ($k->nodeType === XML_TEXT_NODE) { $ziel->appendChild($doc->createTextNode($k->nodeValue)); continue; }
        if ($k->nodeType !== XML_ELEMENT_NODE) continue;
        $tag = strtolower($k->nodeName);
        $tag = $UMBENENNEN[$tag] ?? $tag;
        if (!isset($ERLAUBT[$tag])) { knoten_kopieren($k, $ziel, $doc); continue; }
        $neu = $doc->createElement($tag);
        foreach ($ERLAUBT[$tag] as $attr) {
            if ($k->hasAttribute($attr) && attr_ok($attr, $k->getAttribute($attr))) $neu->setAttribute($attr, $k->getAttribute($attr));
        }
        if ($tag === 'a') { $neu->setAttribute('rel', 'noopener nofollow'); $neu->setAttribute('target', '_blank'); }
        knoten_kopieren($k, $neu, $doc);
        $ziel->appendChild($neu);
    }
}

function html_filtern($roh) {
    if (!class_exists('DOMDocument')) return htmlspecialchars(strip_tags($roh), ENT_QUOTES, 'UTF-8');
    $doc = new DOMDocument();
    libxml_use_internal_errors(true);
    $doc->loadHTML('<?xml encoding="utf-8" ?><div id="w">' . $roh . '</div>', LIBXML_HTML_NOIMPLIED | LIBXML_HTML_NODEFDTD);
    libxml_clear_errors();
    $wurzel = $doc->getElementById('w');
    if (!$wurzel) return '';
    $out = new DOMDocument('1.0', 'UTF-8');
    $frag = $out->createElement('div');
    knoten_kopieren($wurzel, $frag, $out);
    $html = '';
    foreach ($frag->childNodes as $c) $html .= $out->saveHTML($c);
    return trim($html);
}

function laden($datei) {
    if (!file_exists($datei)) return [];
    $daten = json_decode(file_get_contents($datei), true);
    return is_array($daten) ? $daten : [];
}

function speichern($datei, $liste) {
    if (count($liste) > 2000) $liste = array_slice($liste, -2000);
    return file_put_contents($datei, json_encode(array_values($liste), JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)) !== false;
}

function antwort($daten, $status = 200) {
    http_response_code($status);
    echo json_encode($daten, JSON_UNESCAPED_UNICODE);
    exit;
}

function beurteilung_lesen() {
    // Felder einer Kompetenz-Beurteilung: Skala 1..10, Wert 0..Skala, Block, Knoten, Knotentitel
    if (!isset($_POST['skala'], $_POST['wert']) || !ctype_digit((string)$_POST['skala']) || !ctype_digit((string)$_POST['wert'])) return null;
    $skala = (int)$_POST['skala']; $wert = (int)$_POST['wert'];
    if ($skala < 1 || $skala > 10 || $wert < 0 || $wert > $skala) return null;
    return ['art' => 'beurteilung', 'skala' => $skala, 'wert' => $wert, 'block' => mb_substr((string)($_POST['block'] ?? ''), 0, 40),
            'knoten' => mb_substr((string)($_POST['knoten'] ?? ''), 0, 12), 'knotenTitel' => mb_substr((string)($_POST['knotenTitel'] ?? ''), 0, 300)];
}

function moderation_hash() {
    $m = __DIR__ . '/moderation.json';
    if (!file_exists($m)) return '';
    $d = json_decode(file_get_contents($m), true);
    return is_array($d) && isset($d['hash']) ? (string)$d['hash'] : '';
}

function darf($eintrag, $schluessel) {
    // Bearbeiten/Löschen: wer den Kommentar geschrieben hat (eigener Schlüssel) oder wer moderiert
    if (strlen($schluessel) < 16) return false;
    $h = hash('sha256', $schluessel);
    $mod = moderation_hash();
    return (isset($eintrag['sh']) && hash_equals((string)$eintrag['sh'], $h)) || ($mod !== '' && hash_equals($mod, $h));
}

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    if (isset($_GET['ping'])) antwort(['ok' => true, 'backend' => 'php', 'bearbeiten' => true]);
    $seite = (string)($_GET['seite'] ?? '');
    $liste = array_values(array_filter(laden($datei), function ($k) use ($seite) {
        return $seite === '' || empty($k['seite']) || $k['seite'] === $seite;
    }));
    antwort($liste);
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') antwort(['fehler' => 'Nur GET und POST.'], 405);

$aktion = (string)($_POST['aktion'] ?? '');
if (in_array($aktion, ['bearbeiten', 'loeschen', 'pruefen'], true)) {
    $schluessel = (string)($_POST['schluessel'] ?? '');
    if ($aktion === 'pruefen') {
        $mod = moderation_hash();
        antwort(['ok' => $mod !== '' && strlen($schluessel) >= 16 && hash_equals($mod, hash('sha256', $schluessel))]);
    }
    $fp = fopen($sperre, 'c+');
    if (!$fp || !flock($fp, LOCK_EX)) antwort(['fehler' => 'Speichern zurzeit nicht möglich.'], 500);
    $liste = laden($datei);
    $id = (string)($_POST['id'] ?? '');
    $index = null;
    foreach ($liste as $i => $k) { if (($k['id'] ?? '') === $id) { $index = $i; break; } }
    if ($index === null) { flock($fp, LOCK_UN); antwort(['fehler' => 'Kommentar nicht gefunden.'], 404); }
    if (!darf($liste[$index], $schluessel)) { flock($fp, LOCK_UN); antwort(['fehler' => 'Keine Berechtigung für diesen Kommentar.'], 403); }
    if ($aktion === 'loeschen') {
        array_splice($liste, $index, 1);
        $ok = speichern($datei, $liste);
        flock($fp, LOCK_UN);
        antwort($ok ? ['ok' => true] : ['fehler' => 'Speichern nicht möglich.'], $ok ? 200 : 500);
    }
    $text = trim((string)($_POST['text'] ?? ''));
    if (mb_strlen($text) > 20000) { flock($fp, LOCK_UN); antwort(['fehler' => 'Der Kommentar ist zu lang.'], 400); }
    $text = html_filtern($text);
    if (($liste[$index]['art'] ?? '') === 'beurteilung') {
        $b = beurteilung_lesen();
        if (!$b) { flock($fp, LOCK_UN); antwort(['fehler' => 'Ungültige Skala oder ungültiger Wert.'], 400); }
        $liste[$index] = array_merge($liste[$index], $b);
    } elseif (trim(strip_tags($text)) === '' && strpos($text, '<img') === false) { flock($fp, LOCK_UN); antwort(['fehler' => 'Bitte einen Kommentar eingeben.'], 400); }
    $liste[$index]['text'] = $text;
    $liste[$index]['bearbeitet'] = date('c');
    $ok = speichern($datei, $liste);
    flock($fp, LOCK_UN);
    antwort($ok ? ['ok' => true, 'kommentar' => $liste[$index]] : ['fehler' => 'Speichern nicht möglich.'], $ok ? 200 : 500);
}

$name = trim((string)($_POST['name'] ?? ''));
$text = trim((string)($_POST['text'] ?? ''));
$honig = (string)($_POST['website'] ?? '');   // unsichtbares Feld, Menschen lassen es leer

if ($honig !== '') antwort(['ok' => true]);  // Bot: still ignorieren
if (mb_strlen($text) > 20000 || mb_strlen($name) > 80) antwort(['fehler' => 'Der Kommentar ist zu lang.'], 400);
$text = html_filtern($text);
$beurteilung = null;
if (($_POST['art'] ?? '') === 'beurteilung') {
    $beurteilung = beurteilung_lesen();
    if (!$beurteilung) antwort(['fehler' => 'Ungültige Skala oder ungültiger Wert.'], 400);
} elseif (trim(strip_tags($text)) === '' && strpos($text, '<img') === false) antwort(['fehler' => 'Bitte einen Kommentar eingeben.'], 400);

$fp = fopen($sperre, 'c+');
if (!$fp || !flock($fp, LOCK_EX)) antwort(['fehler' => 'Speichern zurzeit nicht möglich.'], 500);

// Frequenzbremse: letzte Zeiten pro Herkunft (Tages-Hash) stehen nur in der Sperrdatei, nie in comments.json
$herkunft = hash('sha256', ($_SERVER['REMOTE_ADDR'] ?? '') . date('Y-m-d'));
$jetzt = time();
$zeiten = json_decode((string)stream_get_contents($fp), true);
if (!is_array($zeiten)) $zeiten = [];
if (isset($zeiten[$herkunft]) && $jetzt - $zeiten[$herkunft] < 10) {
    flock($fp, LOCK_UN);
    antwort(['fehler' => 'Bitte einen Moment warten.'], 429);
}
$zeiten = array_filter($zeiten, function ($t) use ($jetzt) { return $jetzt - $t < 3600; });
$zeiten[$herkunft] = $jetzt;

$schluessel = rtrim(strtr(base64_encode(random_bytes(18)), '+/', '-_'), '=');  // nur für die kommentierende Person
$eintrag = [
    'id' => bin2hex(random_bytes(6)),
    'zeit' => date('c'),
    'name' => $name,
    'text' => $text,
    'sh' => hash('sha256', $schluessel),
];
if ($beurteilung) $eintrag = array_merge($eintrag, $beurteilung);
$seite = (string)($_POST['seite'] ?? '');
if ($seite !== '' && ctype_alnum($seite) && strlen($seite) <= 40) $eintrag['seite'] = $seite;
$liste = laden($datei);
$liste[] = $eintrag;
speichern($datei, $liste);
ftruncate($fp, 0);
rewind($fp);
fwrite($fp, json_encode($zeiten));
flock($fp, LOCK_UN);
fclose($fp);

antwort(['ok' => true, 'kommentar' => $eintrag, 'schluessel' => $schluessel]);
