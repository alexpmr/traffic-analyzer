"""Official firmware announcements, with a persistent outbox and no radio connection."""
from datetime import datetime
import json
import re
import urllib.request

NIGHTLY_URL='https://nightly.meshtastic.org/index.json'
KINDS=('stable','unstable','nightly')
LABELS={'stable':'ESTÁVEL','unstable':'INSTÁVEL','nightly':'NIGHTLY'}

def fetch_json(url):
    request=urllib.request.Request(url,headers={'User-Agent':'TrafficAnalyzer-firmware-notices','Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=15) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('Resposta oficial excede limite')
    return json.loads(raw)

def release_kind(row):
    tag=str(row.get('tag_name') or '').lower()
    if 'nightly' in tag:return 'nightly'
    return 'unstable' if row.get('prerelease') or re.search(r'alpha|beta|rc|preview|dev',tag) else 'stable'

def release_records(rows):
    if not isinstance(rows,list):raise ValueError('Lista de releases inválida')
    result=[]
    for row in rows:
        tag=str(row.get('tag_name') or '') if isinstance(row,dict) else ''
        if not tag or row.get('draft') or not re.fullmatch(r'[A-Za-z0-9_.-]{1,90}',tag):continue
        published=str(row.get('published_at') or row.get('created_at') or '')
        try:stamp=datetime.fromisoformat(published.replace('Z','+00:00')).timestamp()
        except ValueError:continue
        result.append({'id':'github:'+str(row.get('id') or tag),'version':tag,'kind':release_kind(row),
                       'published':stamp,'url':'https://github.com/meshtastic/firmware/releases/tag/'+tag})
    return result

def nightly_record(data):
    if not isinstance(data,dict):raise ValueError('Índice nightly inválido')
    # Official web-flasher consumes id, falling back to version, from this index.
    identity=str(data.get('id') or data.get('version') or '').strip()
    version=str(data.get('version') or identity).strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,90}',identity) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,90}',version):
        raise ValueError('Índice nightly sem versão/build válido')
    return {'id':'nightly:'+identity,'version':version,'kind':'nightly','published':0,
            'url':'https://nightly.meshtastic.org/'}

def message(record,template='Meshtastic {kind}: {version} — {url}'):
    if not isinstance(template,str) or '{{' in template or '}}' in template:raise ValueError('Modelo inválido')
    allowed={'kind','version','url'}
    variables=set(re.findall(r'\{([^{}]+)\}',template))
    if variables!=allowed or len(template)>250:raise ValueError('Modelo deve conter somente {kind}, {version} e {url}')
    text=template.format(kind=LABELS[record['kind']],version=record['version'],url=record['url'])
    if len(text.encode('utf-8'))>200:raise ValueError('Anúncio excede 200 bytes; encurte o modelo')
    return text

def process(state,records,available,enabled,save,send,now,template):
    """One TX per minute; reserve durably before TX. Ambiguous outcomes never retry."""
    ledger=state.setdefault('firmwareOutbox',{})
    initialized=state.setdefault('firmwareInitialized',[])
    for kind in KINDS:
        if kind not in available:continue
        rows=[r for r in records if r['kind']==kind]
        first=kind not in initialized
        if first:initialized.append(kind)
        for record in sorted(rows,key=lambda r:r['published']):
            identity=record['id']
            if identity in ledger:continue
            ledger[identity]={'record':record,'status':'baseline' if first else 'queued' if enabled.get(kind) else 'disabled','attempts':0,'detected':now}
        if not enabled.get(kind):
            for item in ledger.values():
                if item['record']['kind']==kind and item['status']=='queued':item['status']='disabled'
    # A crash after reservation has an unknowable TX outcome: never duplicate it.
    for item in ledger.values():
        if item['status']=='sending':item['status']='uncertain';item['error']='Envio interrompido; consulte histórico antes de repetir'
    # Bound completed history, retaining pending work and recent identities.
    if len(ledger)>2000:
        for key in list(ledger):
            if len(ledger)<=2000:break
            if ledger[key]['status'] in ('sent','baseline','disabled'):del ledger[key]
    save(state)
    if now-state.get('firmwareLastAttempt',0)<60:return False
    for item in ledger.values():
        record=item['record']
        if item['status']!='queued' or not enabled.get(record['kind']) or now<item.get('retryAt',0):continue
        try:text=message(record,template)
        except ValueError as exc:
            item.update(status='failed',error=str(exc));save(state);continue
        item.update(status='sending',attempts=item['attempts']+1)
        state['firmwareLastAttempt']=now
        save(state) # If this fails, transmit nothing.
        try:
            accepted=send(record,text)
        except Exception as exc:
            item.update(status='uncertain',error=str(exc)[:200])
        else:
            if accepted:
                item.update(status='sent',sentAt=now);state['firmwareLastSend']=now
            else:
                item.update(status='queued' if item['attempts']<3 else 'failed',
                            retryAt=now+600*2**(item['attempts']-1),error='Envio recusado pelo backend')
        save(state)
        return item['status']=='sent'
    return False
