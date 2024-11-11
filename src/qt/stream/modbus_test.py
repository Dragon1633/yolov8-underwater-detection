from pymodbus.server.async_io import ModbusTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification
import asyncio
import logging

# 设置日志
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.DEBUG)

# 初始化数据存储，模拟 IO 模块状态
store = ModbusSlaveContext(
    di=None,
    co=ModbusSlaveContext(coils=[0] * 200),  # 初始化120个线圈
    hr=None,
    ir=None
)

# 创建服务器上下文（单从站）
context = ModbusServerContext(slaves=store, single=True)

# 设置设备标识
identity = ModbusDeviceIdentification()
identity.VendorName = 'Pymodbus'
identity.ProductCode = 'PM'
identity.VendorUrl = 'http://github.com/riptideio/pymodbus/'
identity.ProductName = 'Modbus Server'
identity.ModelName = 'Modbus Server'
identity.MajorMinorRevision = '1.0'

async def run_server():
    # 启动 Modbus TCP 服务器
    # server = ModbusTcpServer(context, identity=identity, address=("192.168.1.30", 502))
    server = ModbusTcpServer(context, address=("0.0.0.0", 5020))

    await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(run_server())
