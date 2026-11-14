"""FlagStore con una tabla falsa y un reloj controlado: caché, defaults y set."""

from app.flags import Flag, FlagStore


class FakeTable:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.scans = 0

    def scan(self, **kwargs):
        self.scans += 1
        return {"Items": list(self.items.values())}

    def put_item(self, Item):
        self.items[Item["flag_name"]] = Item


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _store(table: FakeTable, clock: Clock) -> FlagStore:
    return FlagStore(table, ttl_s=5, clock=clock)


async def test_sin_filas_todas_apagadas():
    store = _store(FakeTable(), Clock())
    assert set((await store.all()).values()) == {False}


async def test_set_se_ve_al_instante_en_esta_replica():
    table = FakeTable()
    store = _store(table, Clock())
    await store.set(Flag.FAST_CHARGE_BOOST, True, updated_by="test")
    assert await store.is_enabled(Flag.FAST_CHARGE_BOOST)
    assert table.items["ENABLE_FAST_CHARGE_BOOST"]["updated_by"] == "test"


async def test_cambio_de_otra_replica_se_ve_tras_el_ttl():
    table, clock = FakeTable(), Clock()
    store = _store(table, clock)
    assert not await store.is_enabled(Flag.SIMULATE_CHARGER_FAULT)
    # Otra réplica (u otra persona) enciende la flag directo en la tabla:
    table.items["SIMULATE_CHARGER_HARDWARE_FAULT"] = {
        "flag_name": "SIMULATE_CHARGER_HARDWARE_FAULT",
        "enabled": True,
    }
    clock.now += 4  # dentro de la caché: todavía no se ve
    assert not await store.is_enabled(Flag.SIMULATE_CHARGER_FAULT)
    clock.now += 2  # pasaron 6 s > 5 s: se vuelve a leer
    assert await store.is_enabled(Flag.SIMULATE_CHARGER_FAULT)
    assert table.scans == 2


async def test_nombres_desconocidos_se_ignoran():
    table = FakeTable()
    table.items["FLAG_INVENTADA"] = {"flag_name": "FLAG_INVENTADA", "enabled": True}
    flags = await _store(table, Clock()).all()
    assert "FLAG_INVENTADA" not in flags
    assert len(flags) == 3
