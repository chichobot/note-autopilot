#!/usr/bin/env python3
"""
测试热点扫描的容错机制（多层 fallback）
"""
import json
import subprocess
import sys
from pathlib import Path

def run_command(cmd: list[str], description: str) -> dict:
    """运行命令并返回结果"""
    print(f"\n{'='*60}")
    print(f"测试: {description}")
    print(f"命令: {' '.join(cmd)}")
    print('='*60)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(f"返回码: {result.returncode}")
        
        if result.stdout:
            print(f"\n标准输出:\n{result.stdout[:500]}")
        
        if result.stderr:
            print(f"\n标准错误:\n{result.stderr[:500]}")
        
        # 尝试解析 JSON 输出
        try:
            output_json = json.loads(result.stdout)
            return {
                "success": result.returncode == 0,
                "output": output_json,
                "stderr": result.stderr
            }
        except json.JSONDecodeError:
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "stderr": result.stderr
            }
            
    except subprocess.TimeoutExpired:
        print("❌ 超时")
        return {"success": False, "error": "timeout"}
    except Exception as e:
        print(f"❌ 异常: {e}")
        return {"success": False, "error": str(e)}

def test_topic_scan():
    """测试完整的热点扫描"""
    script_dir = Path(__file__).parent
    topic_scan_sh = script_dir / "topic_scan.sh"
    
    result = run_command(
        ["bash", str(topic_scan_sh)],
        "完整热点扫描（所有数据源）"
    )
    
    if result["success"] and isinstance(result["output"], dict):
        output = result["output"]
        print("\n✅ 热点扫描成功")
        print(f"   候选数量: {len(output.get('candidates', []))}")
        print(f"   数据源健康状态:")
        
        for source, health in output.get("source_health", {}).items():
            status = health.get("status", "unknown")
            items = health.get("details", {}).get("items_collected", 0)
            method = health.get("details", {}).get("method", "")
            print(f"     - {source}: {status} ({items} items) {method}")
        
        return True
    else:
        print("\n❌ 热点扫描失败")
        return False

def test_twitter_fallback():
    """测试 Twitter 浏览器 → twclaw fallback"""
    print("\n" + "="*60)
    print("测试: Twitter 浏览器 fallback 机制")
    print("="*60)
    
    # 模拟浏览器失败的场景
    # 实际测试需要临时禁用 playwright 或修改代码
    print("⚠️  需要手动测试:")
    print("   1. 临时卸载 playwright: pip uninstall playwright")
    print("   2. 运行热点扫描，观察是否降级到 twclaw")
    print("   3. 如果 twclaw 也失败，观察是否跳过 Twitter")
    print("   4. 重新安装 playwright: pip install playwright")
    
    return None

def test_xiaohongshu_fallback():
    """测试小红书 search → feeds → cache fallback"""
    print("\n" + "="*60)
    print("测试: 小红书多层 fallback 机制")
    print("="*60)
    
    print("⚠️  需要手动测试:")
    print("   1. 停止 xiaohongshu-mcp 服务")
    print("   2. 运行热点扫描，观察是否降级到 feeds")
    print("   3. 如果 feeds 失败，观察是否使用历史缓存")
    print("   4. 如果全部失败，观察是否跳过小红书")
    
    return None

def test_all_sources_fail():
    """测试所有数据源失败时的模板 fallback"""
    print("\n" + "="*60)
    print("测试: 所有数据源失败 → 模板 fallback")
    print("="*60)
    
    print("⚠️  需要手动测试:")
    print("   1. 停止所有外部服务（xiaohongshu-mcp）")
    print("   2. 临时禁用网络或修改代码模拟失败")
    print("   3. 运行热点扫描，观察是否使用模板 fallback")
    print("   4. 验证输出包含 5 个固定选题")
    
    return None

def main():
    print("="*60)
    print("Note Autopilot - 容错机制测试")
    print("="*60)
    
    # 测试 1: 完整热点扫描
    test1_pass = test_topic_scan()
    
    # 测试 2: Twitter fallback（手动测试）
    test_twitter_fallback()
    
    # 测试 3: 小红书 fallback（手动测试）
    test_xiaohongshu_fallback()
    
    # 测试 4: 模板 fallback（手动测试）
    test_all_sources_fail()
    
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print(f"✅ 自动测试: {'通过' if test1_pass else '失败'}")
    print("⚠️  手动测试: 需要按照上述步骤手动验证")
    print("\n建议:")
    print("  1. 先确保所有数据源正常工作")
    print("  2. 逐个禁用数据源，验证 fallback 机制")
    print("  3. 检查日志输出，确认降级路径正确")
    
    return 0 if test1_pass else 1

if __name__ == "__main__":
    sys.exit(main())
