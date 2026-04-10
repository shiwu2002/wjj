#!/usr/bin/env python3
"""
HTTP 服务器接口，用于通过 API 调用 PhoneAgent。
"""

import json
import os
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.history import get_history_manager
from phone_agent.model import ModelConfig


app = Flask(__name__)
# 启用 CORS 支持跨域请求
CORS(app)

# 配置文件路径
CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    """从配置文件加载配置。"""
    if not CONFIG_PATH.exists():
        return {}
    
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点。"""
    return jsonify({
        'status': 'healthy',
        'message': 'Server is running'
    })


@app.route('/', methods=['GET'])
def index():
    """返回主页。"""
    from flask import send_from_directory
    return send_from_directory('templates', 'index.html')


@app.route('/devices', methods=['GET'])
def get_devices():
    """获取已连接的设备列表。"""
    try:
        from phone_agent.device_factory import get_device_factory
        device_factory = get_device_factory()
        devices = device_factory.list_devices()
        
        return jsonify({
            'success': True,
            'count': len(devices),
            'devices': [
                {
                    'device_id': d.device_id,
                    'status': d.status,
                    'connection_type': d.connection_type.value,
                    'model': d.model or 'Unknown'
                }
                for d in devices
            ]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/devices/connect', methods=['POST'])
def connect_device():
    """连接到远程设备。"""
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Request must be JSON'
            }), 400
        
        data = request.get_json()
        address = data.get('address', '')
        
        if not address:
            return jsonify({
                'success': False,
                'error': 'Missing device address'
            }), 400
        
        from phone_agent.adb.connection import ADBConnection
        conn = ADBConnection()
        success, message = conn.connect(address)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/devices/disconnect', methods=['POST'])
def disconnect_device():
    """断开远程设备。"""
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Request must be JSON'
            }), 400
        
        data = request.get_json()
        address = data.get('address', 'all')
        
        from phone_agent.adb.connection import ADBConnection
        conn = ADBConnection()
        success, message = conn.disconnect(address if address != 'all' else None)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/devices/refresh', methods=['POST'])
def refresh_devices():
    """刷新设备列表。"""
    try:
        return get_devices()
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/execute', methods=['POST'])
def execute_task():
    """
    执行任务的端点。
    
    请求体 (JSON):
    {
        "task": "要执行的任务描述",
        "model": {  # 可选，覆盖配置文件中的模型配置
            "base_url": "http://localhost:8000/v1",
            "model_name": "autoglm-phone-9b",
            "api_key": "EMPTY"
        },
        "agent": {  # 可选，覆盖配置文件中的代理配置
            "max_steps": 100,
            "device_id": null,
            "lang": "cn",
            "verbose": true
        }
    }
    
    响应 (JSON):
    {
        "success": true,
        "result": "任务执行结果",
        "steps": 10,
        "message": "成功消息"
    }
    """
    try:
        # 检查请求体
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Request must be JSON'
            }), 400
        
        data = request.get_json()
        
        if not data or 'task' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required field: task'
            }), 400
        
        task = data['task']
        
        # 加载配置文件
        config = load_config()
        
        # 使用配置文件中的默认值，允许请求覆盖
        model_config_data = data.get('model', config.get('model', {}))
        agent_config_data = data.get('agent', config.get('agent', {}))
        
        # 创建模型配置
        model_config = ModelConfig(
            base_url=model_config_data.get('base_url', 'http://localhost:8000/v1'),
            model_name=model_config_data.get('model_name', 'autoglm-phone-9b'),
            api_key=model_config_data.get('api_key', 'EMPTY'),
            lang=agent_config_data.get('lang', 'cn')
        )
        
        # 创建代理配置
        agent_config = AgentConfig(
            max_steps=int(agent_config_data.get('max_steps', 100)),
            device_id=agent_config_data.get('device_id'),
            lang=agent_config_data.get('lang', 'cn'),
            verbose=bool(agent_config_data.get('verbose', True))
        )
        
        # 检查是否有可用设备
        from phone_agent.device_factory import get_device_factory
        device_factory = get_device_factory()
        devices = device_factory.list_devices()
        if not devices:
            return jsonify({
                'success': False,
                'error': '没有可用的设备',
                'message': '请先连接 ADB 设备（USB 或无线），刷新页面后重试'
            }), 400
        
        # 创建并运行代理
        agent = PhoneAgent(
            model_config=model_config,
            agent_config=agent_config
        )
        
        # 执行任务
        result = agent.run(task)
        
        # 返回成功响应
        return jsonify({
            'success': True,
            'result': result,
            'steps': agent.step_count,
            'message': 'Task executed successfully'
        })
        
    except Exception as e:
        # 返回错误响应
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Task execution failed'
        }), 500


@app.route('/run', methods=['POST'])
def run_simple():
    """
    简化版的任务执行端点，仅需要任务描述。
    所有配置从 config.json 自动读取。
    
    请求体 (JSON):
    {
        "task": "要执行的任务描述"
    }
    
    响应 (JSON):
    {
        "success": true,
        "result": "任务执行结果",
        "steps": 10
    }
    """
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Request must be JSON'
            }), 400
        
        data = request.get_json()
        
        if not data or 'task' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required field: task'
            }), 400
        
        task = data['task']
        
        # 加载配置文件
        config = load_config()
        
        # 从配置中读取模型和代理配置
        model_config_data = config.get('model', {})
        agent_config_data = config.get('agent', {})
        
        # 创建模型配置
        model_config = ModelConfig(
            base_url=model_config_data.get('base_url', 'http://localhost:8000/v1'),
            model_name=model_config_data.get('model_name', 'autoglm-phone-9b'),
            api_key=model_config_data.get('api_key', 'EMPTY'),
            lang=agent_config_data.get('lang', 'cn')
        )
        
        # 创建代理配置
        agent_config = AgentConfig(
            max_steps=int(agent_config_data.get('max_steps', 100)),
            device_id=agent_config_data.get('device_id'),
            lang=agent_config_data.get('lang', 'cn'),
            verbose=bool(agent_config_data.get('verbose', True))
        )
        
        # 检查是否有可用设备
        from phone_agent.device_factory import get_device_factory
        device_factory = get_device_factory()
        devices = device_factory.list_devices()
        if not devices:
            return jsonify({
                'success': False,
                'error': '没有可用的设备',
                'message': '请先连接 ADB 设备（USB 或无线），刷新页面后重试'
            }), 400
        
        # 创建并运行代理
        agent = PhoneAgent(
            model_config=model_config,
            agent_config=agent_config
        )
        
        # 执行任务
        result = agent.run(task)
        
        # 返回成功响应
        return jsonify({
            'success': True,
            'result': result,
            'steps': agent.step_count
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/config', methods=['GET'])
def get_config():
    """获取当前配置。"""
    config = load_config()
    return jsonify(config)


@app.route('/config', methods=['POST'])
def update_config():
    """更新配置文件。"""
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Request must be JSON'
            }), 400
        
        new_config = request.get_json()
        
        # 保存配置到文件
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_config, f, indent=2, ensure_ascii=False)
        
        return jsonify({
            'success': True,
            'message': 'Configuration updated'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/history', methods=['GET'])
def get_history():
    """获取任务历史记录。"""
    try:
        limit = request.args.get('limit', 100, type=int)
        success_filter = request.args.get('success', type=str)
        
        history_mgr = get_history_manager()
        
        if success_filter == 'true':
            records = history_mgr.get_successful_records(limit=limit)
        elif success_filter == 'false':
            records = history_mgr.get_failed_records(limit=limit)
        else:
            records = history_mgr.get_all_records(limit=limit)
        
        return jsonify({
            'success': True,
            'count': len(records),
            'records': [record.to_dict() for record in records]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/history/clear', methods=['POST'])
def clear_history():
    """清空所有历史记录。"""
    try:
        history_mgr = get_history_manager()
        success = history_mgr.clear_all()
        
        if success:
            return jsonify({
                'success': True,
                'message': '所有历史记录已清空'
            })
        else:
            return jsonify({
                'success': False,
                'error': '清空历史记录失败'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/history/stats', methods=['GET'])
def get_history_stats():
    """获取历史统计信息。"""
    try:
        history_mgr = get_history_manager()
        stats = history_mgr.get_statistics()
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/history/search', methods=['GET'])
def search_history():
    """搜索历史记录。"""
    try:
        keyword = request.args.get('keyword', '')
        limit = request.args.get('limit', 50, type=int)
        
        if not keyword:
            return jsonify({
                'success': False,
                'error': 'Missing required parameter: keyword'
            }), 400
        
        history_mgr = get_history_manager()
        records = history_mgr.search_records(keyword, limit=limit)
        
        return jsonify({
            'success': True,
            'count': len(records),
            'records': [record.to_dict() for record in records]
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    print("=" * 50)
    print("Phone Agent HTTP Server")
    print("=" * 50)
    print("Starting server on http://localhost:5000")
    print("\nAvailable endpoints:")
    print("  GET  /health     - Health check")
    print("  POST /run        - Simple task execution (uses config.json)")
    print("  POST /execute    - Advanced task execution (can override config)")
    print("  GET  /config     - Get current configuration")
    print("  POST /config     - Update configuration")
    print("  GET  /history    - Get task history")
    print("  GET  /history/stats - Get statistics")
    print("  GET  /history/search - Search history")
    print("=" * 50)
    
    # 启动 Flask 服务器
    app.run(host='0.0.0.0', port=5001, debug=False)
