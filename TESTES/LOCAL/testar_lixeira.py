"""API da lixeira: registro, documentos e runtime fictícios isolados, sem processamento."""
import http.client
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding='utf-8')
with tempfile.TemporaryDirectory(prefix='prime-lixeira-') as tmp:
    base = Path(tmp)
    os.environ['AGENTES_PRIME_RUNTIME'] = str(base / 'runtime')
    os.environ['AGENTES_PRIME_REGISTRO_SOL'] = str(base / 'registro.json')
    sys.path.insert(0, str(RAIZ / 'API-LOCAL'))
    import servidor as s
    ids = ['SOL-2026-999991', 'SOL-2026-999992']
    registro = {'solicitacoes': {sol: {'empresa': 'FICTICIA', 'competencia': '2026-09',
                                     'estado': 'AGUARDANDO_SUPERVISOR', 'fluxo': 'DOCUMENTOS'} for sol in ids}}
    original = json.dumps(registro, ensure_ascii=False).encode()
    (base / 'registro.json').write_bytes(original)
    srv = s.iniciar(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s.coordenador.ler_ordem = lambda: None  # não lê nem altera a ordem real
    for sol in ids:
        p = s.RUNTIME / 'execucoes' / sol
        p.mkdir()
        s.gravar_json(p / 'execucao.json', {'sol': sol, 'status': 'CONCLUIDA', 'inicio': '2026-09-01T10:00:00', 'fim': '2026-09-01T10:01:00'})
        (p / 'documento-ficticio.txt').write_text('PRESERVAR', encoding='utf-8')

    def req(m, rota, d=None, token=True):
        c = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=10)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Prime-Sessao'] = srv.token
        c.request(m, '/api' + rota, json.dumps(d) if d is not None else None, headers)
        r = c.getresponse()
        result = (r.status, json.loads(r.read()))
        c.close()
        return result

    try:
        assert len(req('GET', '/solicitacoes')[1]['solicitacoes']) == 2
        assert req('DELETE', '/solicitacoes/' + ids[0], {'confirmado': True}, token=False)[0] == 401
        assert req('DELETE', '/solicitacoes/' + ids[0])[0] == 400
        for indicador in (s.EM_EXECUCAO, s.EM_IMPORTACAO, s.EM_FINANCEIRO):
            indicador['sol'] = ids[0]
            assert req('POST', '/solicitacoes/limpar', {'confirmado': True})[0] == 409
            indicador['sol'] = None
        s.coordenador.ler_ordem = lambda: {'sol': ids[0]}
        assert req('DELETE', '/solicitacoes/' + ids[0], {'confirmado': True})[0] == 409
        s.coordenador.ler_ordem = lambda: None
        p = s.RUNTIME / 'execucoes' / ids[1] / 'execucao.json'
        x = s.ler_json(p)
        s.gravar_json(p, dict(x, status='EM_EXECUCAO'))
        assert req('POST', '/solicitacoes/limpar', {'confirmado': True})[0] == 409
        assert len(req('GET', '/solicitacoes')[1]['solicitacoes']) == 2  # lote atômico
        s.gravar_json(p, x)
        assert req('DELETE', '/solicitacoes/' + ids[0], {'confirmado': True})[0] == 200
        assert req('DELETE', '/solicitacoes/' + ids[0], {'confirmado': True})[1]['total'] == 0
        assert len(req('GET', '/solicitacoes')[1]['solicitacoes']) == 1
        assert sum(req('GET', '/solicitacoes')[1]['contagem'].values()) == 1
        assert len(req('GET', '/solicitacoes/lixeira')[1]['solicitacoes']) == 1
        assert [e['sol'] for e in req('GET', '/estado')[1]['recentes']] == [ids[1]]
        assert req('POST', '/solicitacoes/' + ids[0] + '/financeiro/decisoes', {})[0] == 409
        assert req('POST', '/solicitacoes/' + ids[0] + '/restaurar', {'confirmado': True})[0] == 200
        assert len(req('GET', '/estado')[1]['recentes']) == 2
        assert req('POST', '/solicitacoes/limpar', {'confirmado': True})[1]['total'] == 2
        assert req('GET', '/solicitacoes')[1]['solicitacoes'] == []
        assert req('GET', '/estado')[1]['recentes'] == []
        assert len(req('GET', '/solicitacoes/lixeira')[1]['solicitacoes']) == 2
        assert req('POST', '/solicitacoes/SOL-2026-999999/restaurar', {'confirmado': True})[0] == 404
        assert (base / 'registro.json').read_bytes() == original
        for sol in ids:
            assert (s.RUNTIME / 'execucoes' / sol / 'documento-ficticio.txt').read_text() == 'PRESERVAR'
        assert [e['acao'] for e in s.lixeira_solicitacoes()['eventos']] == ['excluir', 'restaurar', 'excluir', 'excluir']
        print('PASS: excluir/restaurar/limpar; confirmação e autenticação; bloqueio de processamento; limpeza atômica; listas e escritório vazios; auditoria e documentos preservados.')
    finally:
        srv.shutdown()
        srv.server_close()
