import subprocess


def get_ipv4_addresses():
    try:
        # 执行ipconfig命令并捕获输出
        result = subprocess.check_output(
            'ipconfig',
            shell=True,
            stderr=subprocess.STDOUT,
            text=True,  # Python 3.7+可用
            encoding='cp936'  # Windows中文系统编码
        )

        # 提取所有IPv4地址
        ip_addresses = []
        for line in result.splitlines():
            if "IPv4" in line and "地址" in line:  # 适配中文系统
                # 提取冒号后的IP地址部分
                ip = line.split(':')[-1].strip()
                if ip:  # 确保不是空字符串
                    ip_addresses.append(ip)

        return ip_addresses

    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {e.output}")
        return []
    except FileNotFoundError:
        print("未找到ipconfig命令，请确保在Windows系统中运行")
        return []


if __name__ == "__main__":
    # 获取所有IPv4地址
    ip_list = get_ipv4_addresses()

    # 将IP地址分别赋值给变量ip1, ip2, ip3...
    for i, ip in enumerate(ip_list, start=1):
        # globals()[f'ip{i}'] = ip  # 创建全局变量
        if "192.168.1." in ip:
            print("找到IP地址：", ip)

    # 打印所有提取的IP地址
    print("提取到的IPv4地址：")
    for i, ip in enumerate(ip_list, start=1):
        print(f"ip{i} = {ip}")

    # 示例：访问第一个IP地址
    # if ip_list:
    #     print(f"\n第一个IP地址是: {ip1}")
