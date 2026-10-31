"""Process user-selected audio files without starting live capture."""
import argparse
from .settings import Settings
from .session import Session
from .recorder import import_audio, retry_session
from .notes import LocalNotes


def main():
    parser = argparse.ArgumentParser(description='Clicky Classroom offline file processing')
    parser.add_argument('--engine', choices=['whisper','parakeet'], default='parakeet')
    parser.add_argument('--whisper-model', default='base')
    from .models import default_parakeet_directory
    parser.add_argument('--parakeet-directory', default=default_parakeet_directory())
    parser.add_argument('--language', default='en')
    parser.add_argument('--notes-backend', choices=['ollama','openai-local'], default='ollama')
    parser.add_argument('--notes-url', default='http://127.0.0.1:11434')
    parser.add_argument('--notes-model', default='qwen3.5:4b')
    parser.add_argument('--no-notes', action='store_true')
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('import-audio')
    command.add_argument('file')
    command.add_argument('--title', default='Imported class')
    commands.add_parser('retry').add_argument('session')
    commands.add_parser('notes').add_argument('session')
    args = parser.parse_args()
    settings = Settings(engine=args.engine, whisper_model=args.whisper_model,
        parakeet_directory=args.parakeet_directory, language=args.language,
        notes_backend=args.notes_backend, notes_url=args.notes_url, notes_model=args.notes_model,
        automatic_notes=not args.no_notes)
    settings.validate()
    if args.command == 'import-audio':
        session = import_audio(args.file, args.title, settings)
        print('Saved class:', session.path, flush=True)
        retry_session(session, print, settings=settings)
    else:
        session = Session(args.session)
        if args.command == 'retry':
            retry_session(session, print, settings=settings)
        else:
            LocalNotes(settings).generate(session, print)
    print(session.path)


if __name__ == '__main__':
    main()
