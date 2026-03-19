
from contextlib import contextmanager

# XXX: the transport?/protocol?
class AnsiColourDemux:
    def __init__(self, colour_order: tuple[str, ...], stream: asyncio.StreamReader):
        self._colour_order = colour_order
        self._colour_readers: dict[str, asyncio.StreamReader] = {}
        self._stream = stream

    def register_reader(self, colour: str, reader: asyncio.StreamReader):
        self._colour_readers[colour] = reader

        # TODO: future take from self._stream and poke feed_Data and feed_eof etc...
        loop = asyncio.get_running_loop()
        def _read():
            fut = loop.create_task(self._stream.read())
            fut.add_done_callback(lambda data: reader.feed_data(data))
            return fut

        _read()

    def stop(self):
        raise NotImplementedError

# XXXX: This is an absolute hack. We don't really want StreamReader but we pretend
# that it works
class AnsiColourDemuxReader(asyncio.StreamReader):
    def __init__(self, colour_demux: AnsiColourDemux, colour: str):
        super().__init__()

        self._colour_demux = colour_demux
        self._colour = colour

        self._colour_demux.register_reader(colour, self)

    def __repr__(self):
        return f"<AnsiColourDemuxReader colour='{self._colour}' demux={self._colour_demux!r}>"


@contextmanager
def ansi_colour_demux(backend: HardwareBackend, colour_order: tuple[str, ...]) -> Iterator[tuple[asyncio.StreamReader, ...]]:
    colour_demux = AnsiColourDemux(colour_order, backend.output_stream)

    try:
        yield tuple(AnsiColourDemuxReader(colour_demux, c) for c in colour_order)
    finally:
        colour_demux.stop()

