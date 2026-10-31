import asyncio
import httpx


def test_fork_without_releases_does_not_fall_back_to_upstream(monkeypatch):
    import updates
    seen=[]
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url,**kwargs):
            seen.append(url)
            return httpx.Response(404,request=httpx.Request('GET',url))
    monkeypatch.setattr(updates.httpx,'AsyncClient',Client)
    assert asyncio.run(updates.latest()) is None
    assert seen == ['https://api.github.com/repos/CyberBrainiac1/clicky-classroom/releases/latest']
