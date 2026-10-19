"""Query the ripcord warehouse for the fixture target; runs inside the ripcord checkout's uv environment."""
import json
import sys

import duckdb

tables = sys.argv[1]


def rows(sql):
    return duckdb.sql(sql.format(t=tables)).fetchall()


print(json.dumps({
    "functions": sorted(r[0] for r in rows("select name from '{t}/functions.parquet'")),
    "calls": sorted(rows("select c.name, e.name from '{t}/calls.parquet' k join '{t}/functions.parquet' c on k.caller_addr = c.addr join '{t}/functions.parquet' e on k.callee_addr = e.addr")),
    "strings": [r[0] for r in rows("select value from '{t}/strings.parquet'")],
    "peripheral_xrefs": sorted(rows("select f.name, x.ref_type, x.peripheral, x.register_name from '{t}/peripheral_xrefs.parquet' x join '{t}/functions.parquet' f on x.function_addr = f.addr")),
    "recovered_calls": rows("select count(*), count(*) filter (where callee_addr in (select addr from '{t}/functions.parquet')) from '{t}/recovered_calls.parquet'")[0],
    "uart_tx": rows("select string_agg(chr(cast(value as int)), '' order by sequence_idx) from '{t}/mmio_events_boot.parquet' where address = 1073790976 and direction = 'write'")[0][0],
    "mmio_by_function": sorted(rows("select f.name, m.direction, m.peripheral, count(*) from '{t}/mmio_events_boot.parquet' m join '{t}/functions.parquet' f on m.pc >= f.addr and m.pc < f.addr + f.size group by all")),
}))
