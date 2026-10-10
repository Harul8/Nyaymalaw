"""Corpus configuration is lazy, explicit, and independent of model provider."""
from nm.app.composition import Application
from nm.brain.retrieval import HybridSearcher
from nm.arrive.store_directory import FileDirectory
from nm.shared.store_file_store import FileMatterStore
from tests.test_current_brain_app import KEY, ROOT, WiredModel


def application(path, **changes):
    return Application(root=ROOT,model=WiredModel(),store=FileMatterStore(path,key=KEY),
        directory=FileDirectory(path,key=KEY),audit_root=path/'audit',environment={
            'NM_MATTER_KEY':KEY,'NM_MATTER_STORE':str(path), 'NM_MODEL_PROVIDER':'scripted',
            'NM_MODEL_ROUTINE':'scripted-1', 'NM_EMBED_MODEL':'text-embedding-3-large',
            'NM_CORPUS_DIR':str(path/'held-corpus')},**changes)


def test_default_composition_configures_both_corpora_without_loading_or_claiming_ready(tmp_path):
    app=application(tmp_path)
    assert isinstance(app.legal_search,HybridSearcher)
    assert set(app.legal_search.collections)=={'provision','judgment'}
    for collection in app.legal_search.collections.values():
        assert collection._loaded is None and collection.models._loaded is None
        assert collection.corpus_dir==tmp_path/'held-corpus'
    assert app.health()['corpus']=='configured_unverified'
    assert app.health()['brain']['stages'][-2:]==['dispute_decomposition','hybrid_retrieval']


def test_explicit_injection_and_none_preserve_their_owned_configuration(tmp_path):
    injected=object()
    assert application(tmp_path/'injected',legal_search=injected).legal_search is injected
    app=application(tmp_path/'isolated',legal_search=None)
    assert app.legal_search is None and app.health()['corpus']=='not_connected'
