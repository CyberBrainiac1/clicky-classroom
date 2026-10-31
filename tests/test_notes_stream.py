import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import pytest
from classroom.notes import LocalNotes
from classroom.session import Session,RATE
from classroom.settings import Settings


@pytest.mark.parametrize('ending',['complete','truncated','error'])
def test_streamed_local_notes_require_completion_and_unload_on_failure_or_success(tmp_path,monkeypatch,ending):
    monkeypatch.setenv('CLICKY_CLASSROOM_DATA_DIR',str(tmp_path/'data'))
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path,body))
            self.send_response(200)
            self.send_header('Content-Type','application/x-ndjson')
            self.end_headers()
            if self.path=='/api/chat':
                events=[{'message':{'content':'[00:00:00] Work '}} ,{'message':{'content':'changes energy.'}}]
                if ending=='complete':events.append({'done':True})
                elif ending=='error':events.append({'error':'Model failed'})
                for event in events:self.wfile.write(json.dumps(event).encode()+b'\n')
            else:self.wfile.write(b'{"done":true}\n')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        settings=Settings(notes_url=f'http://127.0.0.1:{server.server_port}')
        session=Session.create('Energy',settings)
        session.add_chunk('import',0,RATE)
        session.finish_chunk(session.pending()['id'],'Work changes energy.')
        original=(session.path/'transcript.md').read_bytes()
        if ending=='complete':
            path=LocalNotes(settings).generate(session)
            assert 'Work changes energy.' in path.read_text('utf-8')
        else:
            with pytest.raises(ValueError):LocalNotes(settings).generate(session)
            assert not (session.path/'notes.md').exists()
            assert not list((session.path/'notes-parts').glob('*.md'))
        assert (session.path/'transcript.md').read_bytes()==original
        assert requests[0][1]['stream'] is True
        assert requests[0][1]['options']['num_gpu']==0
        assert requests[-1][0]=='/api/generate' and requests[-1][1]['keep_alive']==0
    finally:
        server.shutdown();server.server_close();worker.join(timeout=2)
