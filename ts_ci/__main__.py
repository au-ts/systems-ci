import sys
from .boards import MACHINE_QUEUE_BOARDS

def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--print-boards':
        print(str(list(MACHINE_QUEUE_BOARDS.keys())).replace("'", '"'))
        exit(0)

if __name__ == "__main__":
    main()
