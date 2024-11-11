import modbus_tk.modbus_tcp as mt
import modbus_tk.defines as cst


master = mt.TcpMaster('127.0.0.1', 5020)
master.set_timeout(1)

try:
    master.execute(slave=1, function_code=cst.WRITE_MULTIPLE_COILS, starting_address=108,
                        quantity_of_x=4, output_value=[1, 0, 0, 0])  # 写多个线圈分别对应绿灯、黄灯、红灯、蜂鸣器
except Exception as e:
    print('error_ok: %s' % e)
