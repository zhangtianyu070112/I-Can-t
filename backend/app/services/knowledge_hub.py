from __future__ import annotations

import math
import hashlib
import json
import re
import time
import zipfile
from io import BytesIO
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.core.config import settings
from app.repo import (
    get_latest_profile_snapshot,
    get_user_dir,
    get_user_events,
    get_user_usages,
    insert_learning_event,
    list_resources,
    read_json,
    write_json,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_MATERIALS_DIR = PROJECT_ROOT / "项目资料"


def _material_path(*parts: str) -> Path:
    """Prefer the organized project-materials folder, with old paths as fallback."""
    organized = PROJECT_MATERIALS_DIR.joinpath(*parts)
    if organized.exists():
        return organized
    return PROJECT_ROOT.joinpath(*parts)


COURSE_DIR = _material_path("课程资料")
SAMPLE_DIR = _material_path("生成示例")
PATH_OUTPUT_DIR = _material_path("第三点_学习路径规划与资源推送", "输出结果")
TEXTBOOK_DIR = PROJECT_ROOT / "uploads" / "textbooks"
CHAPTER_KNOWLEDGE_DIR = TEXTBOOK_DIR / "chapter_knowledge"

# Knowledge-graph concepts are selected from course semantics first.  The
# source documents in the demo library are converted books, so their opening
# pages often contain catalogues, author biographies, publisher blurbs and
# code fragments.  Treating the most frequent token as a concept made entries
# such as “ISBN”, “丛书序” and product names appear in the graph.
GRAPH_DOMAIN_CONCEPTS = (
    "C语言", "数据类型", "变量", "常量", "运算符", "流程控制", "条件语句", "循环语句",
    "函数", "数组", "指针", "结构体", "文件操作", "预处理", "内存管理", "算法", "程序调试",
    "HTML5", "CSS3", "JavaScript", "DOM", "BOM", "语义化标签", "表单", "Canvas", "SVG",
    "Flexbox", "Grid布局", "响应式设计", "事件处理", "Ajax", "WebSocket", "Web Storage",
    "IndexedDB", "动画", "多媒体",
    "Java虚拟机", "JVM", "类加载机制", "运行时数据区", "堆", "栈", "方法区", "垃圾回收",
    "垃圾收集器", "字节码", "JIT", "HotSpot", "双亲委派", "Java内存模型", "性能调优",
    "常量池", "方法调用", "对象创建", "逃逸分析",
    "PHP", "MySQL", "面向对象", "异常处理", "数据库连接", "SQL", "索引", "事务", "查询优化",
    "缓存", "会话管理", "数据库安全",
    "Python", "NumPy", "pandas", "Matplotlib", "数据获取", "数据清洗", "数据预处理",
    "数据分析", "数据可视化", "缺失值", "异常值", "数据聚合", "时间序列",
    "SQL Server", "性能监控", "查询计划", "锁", "死锁", "等待事件", "性能计数器",
    "动态管理视图", "数据库诊断", "备份恢复",
    "区块链", "哈希函数", "数字签名", "共识机制", "工作量证明", "智能合约", "分布式账本",
    "P2P网络", "Merkle树", "比特币", "以太坊", "隐私保护",
    "操作系统", "进程", "线程", "进程调度", "虚拟内存", "文件系统", "中断", "系统调用",
    "设备管理", "同步互斥", "线程同步", "线程互斥", "定时处理", "系统总线", "设备驱动",
    "图形用户界面", "内核", "启动引导", "MBR", "BIOS",
    "数据通信", "信号", "信道", "编码", "调制", "复用", "差错控制", "流量控制", "OSI",
    "TCP/IP", "物理层", "数据链路层", "网络层", "传输层",
    "嵌入式系统", "实时操作系统", "任务调度", "中断处理", "设备驱动", "启动流程",
    "资源管理", "交叉编译", "BSP",
    "物联网", "感知层", "应用层", "传感器", "RFID", "ZigBee", "MQTT", "边缘计算",
    "云计算", "设备接入", "数据采集",
    "安全需求", "威胁建模", "身份认证", "访问控制", "输入验证", "安全编码", "漏洞分析",
    "代码审计", "渗透测试", "加密", "SQL注入", "跨站脚本",
    "软件工程", "软件过程", "需求工程", "需求分析", "用例建模", "软件设计", "体系结构",
    "详细设计", "软件测试", "软件维护", "配置管理", "项目管理", "质量保证", "UML", "敏捷开发",
    "机器学习", "监督学习", "无监督学习", "回归", "分类", "聚类", "特征工程", "模型训练",
    "模型评估", "过拟合", "交叉验证", "决策树", "支持向量机", "神经网络", "scikit-learn",
)

GRAPH_KEYWORD_NOISE_MARKERS = (
    "isbn", "丛书序", "推荐序", "序言", "前言", "内容简介", "作者简介", "译者简介", "编者",
    "出版社", "出版日期", "版权所有", "版权声明", "开发经验丰富", "技术扎实", "职场点拨",
    "疑难问题解", "同事关系", "考虑跳槽", "配套资源下载", "扫码", "二维码", "微信公众号",
    "官方网站", "电子邮箱", "如图所示", "代码清单", "本书", "本章", "读者",
)

GRAPH_GENERIC_TERMS = {
    "一个", "一种", "进行", "实现", "系统", "功能", "主要", "相关", "概述", "介绍", "介绍了",
    "定义", "认识", "目前", "所示", "如图", "内容", "方法", "技术", "特点", "区别", "使用",
    "生成", "开发", "安装", "过程", "应用", "窗口", "管理", "虚拟", "数据", "环境", "运行",
    "机制", "文件",
    "代码", "清单", "基础", "原理", "实践", "小结", "章介绍", "本章小", "子模", "小菜",
    "china", "hello", "turbo", "flash", "downloads", "export", "home", "return", "function",
    "echo", "array", "empty", "null", "true", "false", "https", "http", "br", "ll", "oo", "is",
}

GRAPH_CONCEPT_SUFFIXES = (
    "语言", "类型", "控制", "语句", "函数", "数组", "指针", "结构", "操作", "处理", "管理",
    "算法", "模型", "机制", "架构", "体系", "设计", "编程", "系统", "开发", "过程", "方法",
    "原则", "需求", "测试", "维护", "配置", "工程", "数据库", "网络", "安全", "协议", "线程",
    "进程", "内存", "文件", "调度", "通信", "编码", "调制", "复用", "控制", "视图", "分析",
    "监控", "诊断", "评估", "训练", "学习", "计算", "验证", "审计", "签名", "合约", "账本",
)

GRAPH_COURSE_CONCEPT_HINTS = (
    (("c语言", "手把手教你学c"), (
        "C语言", "数据类型", "变量", "常量", "运算符", "流程控制", "条件语句", "循环语句",
        "函数", "数组", "指针", "结构体", "文件操作", "预处理", "内存管理", "算法", "程序调试",
    )),
    (("html5", "web前端", "javascript"), (
        "HTML5", "CSS3", "JavaScript", "DOM", "BOM", "语义化标签", "表单", "Canvas", "SVG",
        "Flexbox", "Grid布局", "响应式设计", "事件处理", "Ajax", "WebSocket", "Web Storage",
        "IndexedDB", "动画", "多媒体",
    )),
    (("java虚拟机", "jvm"), (
        "Java虚拟机", "JVM", "类加载机制", "运行时数据区", "堆", "栈", "方法区", "垃圾回收",
        "垃圾收集器", "字节码", "JIT", "HotSpot", "双亲委派", "Java内存模型", "性能调优",
        "常量池", "方法调用", "对象创建", "逃逸分析",
    )),
    (("php", "mysql"), (
        "PHP", "MySQL", "函数", "数组", "面向对象", "异常处理", "数据库连接", "SQL", "索引",
        "事务", "查询优化", "缓存", "会话管理", "数据库安全", "输入验证", "SQL注入",
    )),
    (("python数据分析", "数据获取到可视化"), (
        "Python", "NumPy", "pandas", "Matplotlib", "数据获取", "数据清洗", "数据预处理",
        "数据分析", "数据可视化", "缺失值", "异常值", "数据聚合", "时间序列", "机器学习",
    )),
    (("sqlserver", "sql server", "监控和诊断"), (
        "SQL Server", "SQL", "性能监控", "查询计划", "索引", "锁", "死锁", "事务", "等待事件",
        "性能计数器", "动态管理视图", "数据库诊断", "备份恢复", "查询优化",
    )),
    (("区块链",), (
        "区块链", "哈希函数", "数字签名", "共识机制", "工作量证明", "智能合约", "分布式账本",
        "P2P网络", "Merkle树", "比特币", "以太坊", "隐私保护",
    )),
    (("操作系统",), (
        "操作系统", "进程", "线程", "进程调度", "内存管理", "虚拟内存", "文件系统", "中断",
        "系统调用", "设备管理", "同步互斥", "线程同步", "线程互斥", "定时处理", "系统总线",
        "设备驱动", "图形用户界面", "死锁", "内核", "启动引导", "MBR", "BIOS",
    )),
    (("嵌入式",), (
        "嵌入式系统", "实时操作系统", "任务调度", "中断处理", "设备驱动", "启动流程", "内核",
        "资源管理", "交叉编译", "BSP",
    )),
    (("数据通信",), (
        "数据通信", "信号", "信道", "编码", "调制", "复用", "差错控制", "流量控制", "OSI",
        "TCP/IP", "物理层", "数据链路层", "网络层", "传输层",
    )),
    (("物联网",), (
        "物联网", "感知层", "网络层", "应用层", "传感器", "RFID", "ZigBee", "MQTT",
        "边缘计算", "云计算", "设备接入", "数据采集",
    )),
    (("软件安全",), (
        "安全需求", "威胁建模", "身份认证", "访问控制", "输入验证", "安全编码", "漏洞分析",
        "代码审计", "渗透测试", "加密", "SQL注入", "跨站脚本",
    )),
    (("软件工程",), (
        "软件工程", "软件过程", "需求工程", "需求分析", "用例建模", "软件设计", "体系结构",
        "详细设计", "软件测试", "软件维护", "配置管理", "项目管理", "质量保证", "UML", "敏捷开发",
    )),
    (("python机器学习", "机器学习快速入门"), (
        "Python", "机器学习", "监督学习", "无监督学习", "回归", "分类", "聚类", "特征工程",
        "模型训练", "模型评估", "过拟合", "交叉验证", "决策树", "支持向量机", "神经网络",
        "scikit-learn", "NumPy", "pandas", "Matplotlib",
    )),
)

GRAPH_DOMAIN_CONCEPT_SET = {item.lower() for item in GRAPH_DOMAIN_CONCEPTS}

DEFAULT_GRAPH = [
    {
        "id": "req_context",
        "name": "业务场景与问题域",
        "layer": "需求发现",
        "difficulty": 1,
        "desc": "明确业务目标、用户角色、边界和约束，防止后续建模偏离真实场景。",
        "keywords": ["业务场景", "用户", "边界", "问题域"],
    },
    {
        "id": "req_stakeholder",
        "name": "干系人与访谈",
        "layer": "需求发现",
        "difficulty": 1,
        "desc": "识别干系人并设计访谈问题，把隐性需求转化为可分析材料。",
        "keywords": ["干系人", "访谈", "需求调研"],
    },
    {
        "id": "req_usecase",
        "name": "用例建模",
        "layer": "需求建模",
        "difficulty": 2,
        "desc": "用参与者、用例、主成功场景和扩展场景描述系统行为。",
        "keywords": ["用例", "参与者", "场景", "UML"],
    },
    {
        "id": "req_domain",
        "name": "领域模型",
        "layer": "需求建模",
        "difficulty": 2,
        "desc": "抽取领域对象、属性与关系，为数据库设计和业务规则实现打基础。",
        "keywords": ["领域模型", "类图", "对象", "关系"],
    },
    {
        "id": "req_nonfunctional",
        "name": "非功能需求",
        "layer": "质量约束",
        "difficulty": 2,
        "desc": "从性能、安全、可靠性、可用性和可维护性描述系统质量。",
        "keywords": ["非功能需求", "性能", "安全", "可靠性"],
    },
    {
        "id": "req_priority",
        "name": "需求优先级",
        "layer": "质量约束",
        "difficulty": 2,
        "desc": "用 MoSCoW、价值/成本矩阵等方法确定阶段实现顺序。",
        "keywords": ["优先级", "MoSCoW", "价值", "成本"],
    },
    {
        "id": "req_trace",
        "name": "需求追踪矩阵",
        "layer": "验证闭环",
        "difficulty": 3,
        "desc": "把目标、需求、设计、测试和资源关联起来，支撑评审与变更控制。",
        "keywords": ["追踪矩阵", "测试", "变更", "验证"],
    },
    {
        "id": "req_review",
        "name": "需求评审与验收",
        "layer": "验证闭环",
        "difficulty": 3,
        "desc": "通过评审清单、验收标准和原型验证降低需求歧义和返工风险。",
        "keywords": ["评审", "验收", "原型", "歧义"],
    },
]

DEFAULT_EDGES = [
    {"source": "req_context", "target": "req_usecase", "label": "场景驱动"},
    {"source": "req_stakeholder", "target": "req_usecase", "label": "访谈输入"},
    {"source": "req_usecase", "target": "req_domain", "label": "对象抽取"},
    {"source": "req_domain", "target": "req_trace", "label": "设计映射"},
    {"source": "req_nonfunctional", "target": "req_priority", "label": "约束排序"},
    {"source": "req_priority", "target": "req_trace", "label": "计划落地"},
    {"source": "req_trace", "target": "req_review", "label": "闭环验证"},
]


def overview(student_id: str) -> dict[str, Any]:
    docs = _collect_documents(student_id)
    resources = list_resources(student_id)
    events = get_user_events(student_id)
    usages = get_user_usages(student_id)
    profile = get_latest_profile_snapshot(student_id) or {}
    graph = graph_data(student_id)
    mastery = mastery_data(student_id)

    source_types = Counter(d["source_type"] for d in docs)
    return {
        "stats": {
            "course_documents": source_types.get("course_material", 0),
            "generated_resources": len(resources),
            "indexed_chunks": len(docs),
            "knowledge_nodes": len(graph["nodes"]),
            "learning_events": len(events),
            "feedback_records": len(usages),
            "average_mastery": mastery["summary"]["average_mastery"],
        },
        "profile": {
            "id": profile.get("id"),
            "knowledge_base_level": profile.get("knowledge_base_level", "待画像"),
            "cognitive_style": profile.get("cognitive_style", "待画像"),
            "modality_preference": profile.get("modality_preference", "待画像"),
            "mistake_patterns": profile.get("mistake_patterns", "待采集"),
        },
        "pipeline": [
            {"name": "课程资料解析", "status": "ready", "count": source_types.get("course_material", 0)},
            {"name": "生成资源沉淀", "status": "ready", "count": len(resources)},
            {"name": "轻量RAG检索", "status": "ready", "count": len(docs)},
            {"name": "掌握度闭环", "status": "ready", "count": len(mastery["nodes"])},
        ],
        "top_sources": [
            {
                "title": d["title"],
                "source_type": d["source_type"],
                "chars": len(d["text"]),
            }
            for d in docs[:8]
        ],
        "activity": _activity_feed(student_id),
    }


def search_index(student_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    docs = _collect_documents(student_id)
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    q_counter = Counter(q_tokens)
    results: list[dict[str, Any]] = []
    for doc in docs:
        tokens = doc.get("tokens") or _tokenize(doc["title"] + "\n" + doc["text"])
        if not tokens:
            continue
        token_counter = Counter(tokens)
        common = set(q_counter) & set(token_counter)
        if not common:
            title_hit = any(k in doc["title"] for k in query.split())
            if not title_hit:
                continue
        score = _cosine(q_counter, token_counter)
        title_boost = 0.18 if any(t in _tokenize(doc["title"]) for t in q_tokens) else 0
        source_boost = 0.06 if doc["source_type"] in {"generated_resource", "course_material"} else 0
        final_score = min(1.0, score + title_boost + source_boost)
        if final_score <= 0.01:
            continue
        results.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "source_type": doc["source_type"],
                "resource_type": doc.get("resource_type", ""),
                "score": round(final_score, 4),
                "excerpt": _excerpt(doc["text"], q_tokens),
                "path": doc.get("path", ""),
                "tags": doc.get("tags", []),
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[: max(1, min(limit, 10))]


def format_references(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""
    parts = ["[知识库检索参考]"]
    for idx, item in enumerate(results[:5], 1):
        parts.append(f"{idx}. 来源：{item['title']}；匹配度：{item['score']}")
        parts.append(item["excerpt"][:520])
    return "\n".join(parts)


def ingest_textbook(student_id: str, filename: str, content: bytes) -> dict[str, Any]:
    safe_name = Path(filename or "电子教材.txt").name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in {".txt", ".md", ".pdf", ".docx"}:
        raise ValueError("仅支持 TXT、Markdown、PDF 和 Word 电子教材")
    if not content:
        raise ValueError("上传的教材文件为空")
    if len(content) > 30 * 1024 * 1024:
        raise ValueError("教材文件不能超过 30MB")

    text = _extract_textbook_text(content, suffix)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 40:
        raise ValueError("教材中可识别的正文过少，无法生成知识结构")

    textbook_id = hashlib.sha256(content).hexdigest()[:16]
    TEXTBOOK_DIR.mkdir(parents=True, exist_ok=True)
    CHAPTER_KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{textbook_id}{suffix}"
    (TEXTBOOK_DIR / stored_name).write_bytes(content)

    chapters = _build_uploaded_textbook_chapters(text, Path(safe_name).stem)
    payload = {
        "textbook_id": textbook_id,
        "filename": safe_name,
        "content_hash": textbook_id,
        "core_topic": Path(safe_name).stem,
        "chapter_count": len(chapters),
        "total_kp_count": sum(len(item.get("keywords", [])) for item in chapters),
        "chapters": chapters,
    }
    write_json(CHAPTER_KNOWLEDGE_DIR / f"book_{textbook_id}.json", payload)
    index_path = CHAPTER_KNOWLEDGE_DIR / "index.json"
    index = read_json(index_path, {})
    if not isinstance(index, dict):
        index = {}
    index[textbook_id] = {"filename": safe_name, "student_id": student_id, "uploaded_at": datetime.now(timezone.utc).isoformat()}
    write_json(index_path, index)
    insert_learning_event(student_id, "textbook_uploaded", {
        "textbook_id": textbook_id,
        "filename": safe_name,
        "chapter_count": len(chapters),
        "concept_count": payload["total_kp_count"],
    })
    return {
        "textbook_id": textbook_id,
        "course_id": f"textbook:{textbook_id}",
        "filename": safe_name,
        "chapter_count": len(chapters),
        "concept_count": payload["total_kp_count"],
    }


def _extract_textbook_text(content: bytes, suffix: str) -> str:
    if suffix in {".txt", ".md"}:
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("教材文本编码无法识别")
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                xml = archive.read("word/document.xml")
            root = ET.fromstring(xml)
            paragraphs = []
            for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                line = "".join(node.text or "" for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")).strip()
                if line:
                    paragraphs.append(line)
            return "\n".join(paragraphs)
        except Exception as exc:
            raise ValueError("Word 教材解析失败，请确认文件未损坏") from exc
    try:
        import fitz
        document = fitz.open(stream=content, filetype="pdf")
        pages = [page.get_text("text").strip() for page in document]
        document.close()
        return "\n\n".join(page for page in pages if page)
    except Exception as exc:
        raise ValueError("PDF 教材无法提取正文，请使用可复制文字的 PDF") from exc


def _build_uploaded_textbook_chapters(text: str, title: str) -> list[dict[str, Any]]:
    heading_pattern = re.compile(
        r"(?m)^\s*(第\s*[一二三四五六七八九十百零〇\d]+\s*(?:章|节|篇|部分)\s*[^\n]{0,48}|\d+(?:\.\d+){0,3}\s+[^\n]{2,48}|[一二三四五六七八九十]+[、.]\s*[^\n]{2,48})\s*$"
    )
    matches = list(heading_pattern.finditer(text))[:40]
    sections: list[tuple[str, str]] = []
    if matches:
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if len(body) >= 30:
                sections.append((match.group(1).strip(), body))
    if not sections:
        chunk_size = 5000
        sections = [
            (f"{title}·第{index + 1}部分", text[start:start + chunk_size])
            for index, start in enumerate(range(0, min(len(text), chunk_size * 20), chunk_size))
            if text[start:start + chunk_size].strip()
        ]

    chapters = []
    for index, (chapter_title, body) in enumerate(sections):
        keywords = _extract_graph_keywords(body, chapter_title, 14)
        summary_source = re.sub(r"\s+", " ", body)
        summary = summary_source[:180] + ("…" if len(summary_source) > 180 else "")
        chapters.append({
            "chapter_title": chapter_title,
            "chapter_index": index,
            "keywords": keywords,
            "summary": summary,
            "char_count": len(body),
            "knowledge_points": [
                {"id": _stable_id("textbook-concept", f"{title}:{chapter_title}:{keyword}"), "title": keyword, "keywords": [keyword], "chapter": chapter_title}
                for keyword in keywords
            ],
        })
    return chapters


def graph_data(
    student_id: str,
    course: str = "",
    source_type: str = "all",
    keyword: str = "",
    max_nodes: int = 56,
) -> dict[str, Any]:
    profile = get_latest_profile_snapshot(student_id) or {}
    weak_text = " ".join(str(x) for x in (profile.get("evidence") or {}).get("weak_points", []))
    weak_text += " " + str(profile.get("mistake_patterns", ""))
    state = _read_state(student_id)
    resources = list_resources(student_id)
    sources = _graph_sources(student_id)
    if not sources:
        return {
            "course": "暂无课程",
            "selected_course": "",
            "courses": [],
            "nodes": [],
            "edges": [],
            "legend": _graph_legend(),
            "stats": {"documents": 0, "chapters": 0, "concepts": 0, "relations": 0},
        }

    selected = next(
        (item for item in sources if course and course in {item["id"], item["title"]}),
        sources[0],
    )
    selected = _hydrate_graph_source(selected)
    max_nodes = max(12, min(int(max_nodes), 100))
    nodes, edges = _build_course_graph(selected, resources, weak_text, state, source_type, max_nodes)

    normalized_keyword = keyword.strip().lower()
    if normalized_keyword:
        matching = {
            node["id"]
            for node in nodes
            if normalized_keyword in " ".join(
                [node.get("name", ""), node.get("desc", ""), " ".join(node.get("keywords", []))]
            ).lower()
        }
        connected = {
            endpoint
            for edge in edges
            if edge["source"] in matching or edge["target"] in matching
            for endpoint in (edge["source"], edge["target"])
        }
        keep = matching | connected | {selected["id"]}
        nodes = [node for node in nodes if node["id"] in keep]
        edges = [edge for edge in edges if edge["source"] in keep and edge["target"] in keep]

    degree = Counter()
    for edge in edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    nodes = [{**node, "relation_count": degree[node["id"]]} for node in nodes]

    chapter_count = len([node for node in nodes if node["kind"] == "chapter"])
    concept_count = len([node for node in nodes if node["kind"] == "concept"])
    return {
        "course": selected["title"],
        "selected_course": selected["id"],
        "course_summary": selected.get("summary", ""),
        "courses": [
            {
                "id": item["id"],
                "title": item["title"],
                "source_type": item["source_type"],
                "chapter_count": len(item.get("chapters", [])),
                "concept_count": sum(len(chapter.get("keywords", [])) for chapter in item.get("chapters", [])),
            }
            for item in sources
        ],
        "nodes": nodes,
        "edges": edges,
        "legend": _graph_legend(),
        "stats": {
            "documents": 1,
            "chapters": chapter_count,
            "concepts": concept_count,
            "relations": len(edges),
        },
    }


def _graph_sources(student_id: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    index = _read_json_file(CHAPTER_KNOWLEDGE_DIR / "index.json")
    if isinstance(index, dict):
        for textbook_id, metadata in index.items():
            owner = str(metadata.get("student_id") or "") if isinstance(metadata, dict) else ""
            if owner and owner != student_id:
                continue
            payload = _read_json_file(CHAPTER_KNOWLEDGE_DIR / f"book_{textbook_id}.json")
            if not isinstance(payload, dict):
                continue
            title = Path(str(payload.get("filename") or metadata.get("filename") or textbook_id)).stem
            chapters = _deduplicate_chapters(payload.get("chapters") or [])
            sources.append(
                {
                    "id": f"textbook:{textbook_id}",
                    "title": title,
                    "source_type": "uploaded_textbook",
                    "path": str(CHAPTER_KNOWLEDGE_DIR / f"book_{textbook_id}.json"),
                    "summary": f"由上传教材自动解析，共识别 {len(chapters)} 个章节。",
                    "chapters": chapters,
                }
            )
            seen_titles.add(title)

    for path in sorted(COURSE_DIR.glob("*")) if COURSE_DIR.exists() else []:
        if not path.is_file() or path.stem in seen_titles:
            continue
        sources.append(
            {
                "id": f"course_material:{path.name}",
                "title": path.stem.replace("_", " "),
                "source_type": "course_material",
                "path": str(path),
                "summary": "课程资料库中的原始教学文档，选择后按正文内容提取知识模块。",
                "chapters": [],
            }
        )

    # The course selector represents source-of-truth teaching documents only.
    # Generated question banks, lecture notes, practice cases, QA reports,
    # extended readings and path outputs remain available as related resource
    # nodes, but must never be parsed as if they were courses.
    sources.sort(key=lambda item: (0 if item["source_type"] == "uploaded_textbook" else 1, item["title"]))
    return sources


def _hydrate_graph_source(source: dict[str, Any]) -> dict[str, Any]:
    if source.get("chapters"):
        return source
    path = Path(str(source.get("path", "")))
    text = _read_text(path)
    if not text:
        return source
    doc = {
        "id": source["id"],
        "title": source["title"],
        "source_type": source["source_type"],
        "path": source.get("path", ""),
        "text": text,
        "tags": _guess_tags(source["title"] + "\n" + text),
    }
    return {
        **source,
        "summary": _clean_summary(text, 180),
        "chapters": _document_modules(doc),
    }


def _build_course_graph(
    source: dict[str, Any],
    resources: list[dict[str, Any]],
    weak_text: str,
    state: dict[str, Any],
    source_filter: str,
    max_nodes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root_id = source["id"]
    nodes: list[dict[str, Any]] = [
        {
            "id": root_id,
            "name": source["title"],
            "kind": "course",
            "layer": "课程",
            "category": "课程中心",
            "difficulty": 1,
            "desc": source.get("summary") or "课程知识结构总览",
            "keywords": [source["title"]],
            "source_title": source["title"],
            "source_type": source["source_type"],
            "source_path": source.get("path", ""),
            "mastery": 0,
            "status": "available",
        }
    ]
    edges: list[dict[str, Any]] = []
    concept_nodes: dict[str, str] = {}
    chapters = source.get("chapters", [])

    if source_filter != "generated":
        available_slots = max_nodes - 1
        chapter_limit = min(len(chapters), max(3, available_slots // 4))
        selected_chapters = chapters[:chapter_limit]
        concept_slots = max(0, available_slots - len(selected_chapters))
        per_chapter = max(2, min(5, concept_slots // max(1, len(selected_chapters))))
        previous_chapter_id = ""
        for chapter_index, chapter in enumerate(selected_chapters):
            chapter_name = str(chapter.get("chapter_title") or f"知识模块 {chapter_index + 1}")
            chapter_id = _stable_id("chapter", f"{root_id}:{chapter_name}")
            semantic_keywords = _extract_graph_keywords(
                f"{chapter_name}\n{chapter.get('summary', '')}",
                source["title"],
                per_chapter * 2,
            )
            keywords = _clean_course_keywords(
                [*semantic_keywords, *(chapter.get("keywords") or [])],
                source["title"],
            )[:per_chapter]
            chapter_node = {
                "id": chapter_id,
                "name": chapter_name,
                "kind": "chapter",
                "layer": "章节与模块",
                "category": "课程章节",
                "difficulty": min(3, 1 + chapter_index // 5),
                "desc": _clean_summary(chapter.get("summary", ""), 220),
                "keywords": keywords,
                "source_title": source["title"],
                "source_type": source["source_type"],
                "source_path": source.get("path", ""),
                "chapter": chapter_name,
            }
            nodes.append(_with_mastery(chapter_node, state, resources, weak_text, chapter_index))
            edges.append({"source": root_id, "target": chapter_id, "label": "包含", "type": "hierarchy"})
            if previous_chapter_id:
                edges.append({"source": previous_chapter_id, "target": chapter_id, "label": "学习顺序", "type": "path"})
            previous_chapter_id = chapter_id

            for keyword_index, concept in enumerate(keywords):
                normalized = concept.lower()
                concept_id = concept_nodes.get(normalized)
                if not concept_id:
                    concept_id = _stable_id("concept", f"{root_id}:{normalized}")
                    concept_nodes[normalized] = concept_id
                    concept_node = {
                        "id": concept_id,
                        "name": concept,
                        "kind": "concept",
                        "layer": "核心知识点",
                        "category": "核心知识点",
                        "difficulty": min(3, 1 + (chapter_index + keyword_index) // 7),
                        "desc": f"“{concept}”是“{chapter_name}”中的核心概念，来源于课程文档关键词与章节内容解析。",
                        "keywords": [concept, chapter_name],
                        "source_title": source["title"],
                        "source_type": source["source_type"],
                        "source_path": source.get("path", ""),
                        "chapter": chapter_name,
                    }
                    nodes.append(_with_mastery(concept_node, state, resources, weak_text, len(nodes)))
                edges.append({"source": chapter_id, "target": concept_id, "label": "关键概念", "type": "knowledge"})

    if source_filter != "course":
        for resource in resources:
            if len(nodes) >= max_nodes:
                break
            resource_text = " ".join(
                [str(resource.get("title", "")), " ".join(map(str, resource.get("tags", []))), str(resource.get("type", ""))]
            )
            related = source_filter == "generated" or source["title"] in resource_text or any(
                concept in resource_text for concept in list(concept_nodes)[:20]
            )
            if not related:
                continue
            resource_id = f"resource:{resource.get('id')}"
            nodes.append(
                {
                    "id": resource_id,
                    "name": resource.get("title") or "个性化学习资源",
                    "kind": "resource",
                    "layer": "学习资源",
                    "category": "个性化资源",
                    "difficulty": 1,
                    "desc": f"由多智能体生成的 {resource.get('type') or '学习'} 资源，可用于巩固本课程知识点。",
                    "keywords": list(map(str, resource.get("tags", [])))[:5],
                    "source_title": resource.get("title") or "生成资源",
                    "source_type": "generated_resource",
                    "source_path": str(resource.get("content_uri", "")),
                    "mastery": 0,
                    "status": "available",
                }
            )
            edges.append({"source": root_id, "target": resource_id, "label": "配套资源", "type": "resource"})

    nodes = nodes[:max_nodes]
    keep_ids = {node["id"] for node in nodes}
    edges = [edge for edge in edges if edge["source"] in keep_ids and edge["target"] in keep_ids]
    child_mastery = [
        float(node["mastery"])
        for node in nodes[1:]
        if node["kind"] != "resource" and int(node.get("evidence_count") or 0) > 0
    ]
    nodes[0]["mastery"] = round(sum(child_mastery) / len(child_mastery), 1) if child_mastery else 0
    nodes[0]["evidence_count"] = sum(int(node.get("evidence_count") or 0) for node in nodes[1:])
    nodes[0]["status"] = _node_status(nodes[0]["mastery"], 0) if child_mastery else "unassessed"
    return nodes, edges


def _with_mastery(
    node: dict[str, Any],
    state: dict[str, Any],
    resources: list[dict[str, Any]],
    weak_text: str,
    index: int,
) -> dict[str, Any]:
    record = state.get("nodes", {}).get(node["id"], {})
    evidence_count = int(record.get("attempts") or len(record.get("history") or []))
    mastery = float(record.get("mastery", 0)) if evidence_count else 0
    return {
        **node,
        "mastery": round(mastery, 1),
        "evidence_count": evidence_count,
        "status": _node_status(mastery, index) if evidence_count else "unassessed",
    }


def _document_modules(doc: dict[str, Any]) -> list[dict[str, Any]]:
    keywords = _extract_graph_keywords(doc.get("text", ""), doc.get("title", ""), 24)
    if not keywords:
        keywords = doc.get("tags", []) or [doc.get("title", "课程概览")]
    module_names = ["基础概念", "核心原理", "方法与技术", "实践与应用"]
    modules: list[dict[str, Any]] = []
    chunk_size = max(3, math.ceil(len(keywords) / len(module_names)))
    for index, name in enumerate(module_names):
        chunk = keywords[index * chunk_size : (index + 1) * chunk_size]
        if not chunk:
            continue
        modules.append(
            {
                "chapter_title": name,
                "chapter_index": index,
                "keywords": chunk,
                "summary": f"从《{doc.get('title', '课程文档')}》正文中提取的{name}知识集合。",
            }
        )
    return modules


def _extract_graph_keywords(text: str, title: str, limit: int) -> list[str]:
    content = str(text or "")
    content_lower = content.lower()
    title_lower = title.lower()
    matched_course_concepts = _matched_course_domain_concepts(title)
    course_concepts = matched_course_concepts or GRAPH_DOMAIN_CONCEPTS
    allowed_course_concepts = {item.lower() for item in course_concepts}
    ranked_domain: list[tuple[float, int, str]] = []
    for order, concept in enumerate(course_concepts):
        count = content_lower.count(concept.lower())
        if not count:
            continue
        score = count * 3 + min(len(concept), 12) + (24 if concept.lower() in title_lower else 0)
        ranked_domain.append((-score, order, concept))
    ranked_domain.sort()

    selected = _clean_keywords([item[2] for item in ranked_domain], title)
    if len(selected) >= limit or (matched_course_concepts and len(selected) >= 6):
        return selected[:limit]

    # Fallback for an uploaded course outside the built-in domain vocabulary.
    # It is intentionally conservative: only repeated, concept-shaped phrases
    # may supplement the semantic dictionary.
    phrases = re.split(
        r"[，。；、：:（）()\s]+|(?:以及|并且|或者|包括|包含|通过|用于|属于|作为|和|与|及|是|为|的)",
        content,
    )
    raw = [
        item.strip()
        for item in phrases
        if re.fullmatch(r"[\u4e00-\u9fff]{2,14}|[A-Za-z][A-Za-z0-9+#. -]{1,24}", item.strip())
    ]
    raw.extend(re.findall(r"[A-Za-z][A-Za-z0-9+#.]{1,20}|[\u4e00-\u9fff]{2,12}", content))
    counts = Counter(item.strip() for item in raw if item.strip())
    fallback = [
        term
        for term, count in counts.most_common(320)
        if count >= 2
        and _is_graph_keyword_candidate(term, title)
        and (term.lower() in allowed_course_concepts or term.lower() not in GRAPH_DOMAIN_CONCEPT_SET)
    ]
    return _clean_keywords([*selected, *fallback], title)[:limit]


def _matched_course_domain_concepts(title: str) -> tuple[str, ...]:
    title_lower = str(title or "").lower()
    selected: list[str] = []
    for hints, concepts in GRAPH_COURSE_CONCEPT_HINTS:
        if any(hint in title_lower for hint in hints):
            selected.extend(concepts)
    return tuple(dict.fromkeys(selected))


def _deduplicate_chapters(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    display_titles: dict[str, tuple[int, str]] = {}
    for chapter in chapters:
        display_title = _chapter_display_title(chapter)
        title = re.sub(r"\s+", "", display_title).lower()
        if not title:
            continue
        chapter_number = re.match(r"第\s*(\d+)\s*章", display_title)
        key = f"chapter:{int(chapter_number.group(1))}" if chapter_number else title
        current = selected.get(key)
        if current is None or int(chapter.get("char_count", 0)) > int(current.get("char_count", 0)):
            selected[key] = dict(chapter)
        unusual = len(re.findall(r"[^\w\s\u4e00-\u9fffA-Za-z0-9：:（）()、·.+#/-]", display_title))
        incomplete = 1 if re.search(r"(?:的|和|与)$", display_title) else 0
        title_score = min(len(display_title), 72) - unusual * 40 - incomplete * 20
        if key not in display_titles or title_score > display_titles[key][0]:
            display_titles[key] = (title_score, display_title)
    for key, chapter in selected.items():
        chapter["chapter_title"] = display_titles.get(key, (0, str(chapter.get("chapter_title", ""))))[1]
    return sorted(selected.values(), key=lambda item: int(item.get("chapter_index", 0)))


def _chapter_display_title(chapter: dict[str, Any]) -> str:
    original = re.sub(r"\s+", " ", str(chapter.get("chapter_title", ""))).strip()
    first_line = str(chapter.get("summary", "")).splitlines()[0].strip()
    first_line = re.sub(r"[\t ]+\d+\s*$", "", first_line)
    first_line = re.sub(r"\s+", " ", first_line).strip()
    if re.match(r"第\s*\d+\s*章", first_line) and len(first_line) <= 80:
        return first_line
    return original


def _clean_keywords(values: list[Any], title: str = "") -> list[str]:
    output: list[str] = []
    for value in values:
        term = re.sub(r"\s+", " ", str(value)).strip(" -_、，。:：")
        if not _is_graph_keyword_candidate(term, title):
            continue
        if term not in output:
            output.append(term)
    return output


def _clean_course_keywords(values: list[Any], title: str) -> list[str]:
    cleaned = _clean_keywords(values, title)
    course_concepts = _matched_course_domain_concepts(title)
    if not course_concepts:
        return cleaned
    allowed = {item.lower() for item in course_concepts}
    return [item for item in cleaned if item.lower() in allowed]


def _is_graph_keyword_candidate(term: str, title: str = "") -> bool:
    normalized = re.sub(r"\s+", " ", str(term or "")).strip(" -_、，。:：")
    lowered = normalized.lower()
    if len(normalized) < 2 or len(normalized) > 18 or normalized.isdigit():
        return False
    if lowered in GRAPH_GENERIC_TERMS or any(marker in lowered for marker in GRAPH_KEYWORD_NOISE_MARKERS):
        return False
    if any(char.isdigit() for char in normalized) and not re.search(r"[A-Za-z]", normalized):
        return False
    if re.search(r"(?:了|着|过|丰富|扎实|目前|所示)$", normalized):
        return False
    if lowered in GRAPH_DOMAIN_CONCEPT_SET:
        return True
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9+#. /-]*", normalized):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]{2,}", normalized)) and normalized.endswith(GRAPH_CONCEPT_SUFFIXES)


def _clean_summary(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    return clean[:limit] + ("…" if len(clean) > limit else "")


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha1(value.encode('utf-8')).hexdigest()[:12]}"


def _read_json_file(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _graph_legend() -> list[dict[str, str]]:
    return [
        {"category": "课程中心", "label": "当前课程", "color": "#1769e8"},
        {"category": "课程章节", "label": "章节模块", "color": "#18a874"},
        {"category": "核心知识点", "label": "核心知识点", "color": "#7c5ce7"},
        {"category": "个性化资源", "label": "个性化资源", "color": "#f59e0b"},
    ]


def mastery_data(student_id: str) -> dict[str, Any]:
    graph = graph_data(student_id)
    state = _read_state(student_id)
    now = time.time()
    nodes: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []

    for node in graph["nodes"]:
        record = state.get("nodes", {}).get(node["id"], {})
        evidence_count = int(record.get("attempts") or len(record.get("history") or []))
        last_review = float(record.get("last_review_ts", 0)) if evidence_count else 0
        mastery = float(record.get("mastery", 0)) if evidence_count else 0
        decayed = _decayed_mastery(mastery, last_review, now) if evidence_count else 0
        item = {
            **node,
            "mastery": mastery,
            "current_mastery": decayed,
            "last_review_ts": last_review,
            "evidence_count": evidence_count,
            "status": _node_status(decayed, 0) if evidence_count else "unassessed",
        }
        nodes.append(item)
        if evidence_count and mastery >= 70 and decayed < 70:
            review.append({"id": node["id"], "name": node["name"], "current_mastery": decayed})

    assessed_nodes = [node for node in nodes if int(node.get("evidence_count") or 0) > 0]
    avg = round(sum(n["current_mastery"] for n in assessed_nodes) / len(assessed_nodes), 1) if assessed_nodes else 0
    completed = len([n for n in assessed_nodes if n["current_mastery"] >= 80])
    in_progress = len([n for n in assessed_nodes if 50 <= n["current_mastery"] < 80])
    dimensions = _dimension_scores(assessed_nodes)

    return {
        "summary": {
            "average_mastery": avg,
            "completed_nodes": completed,
            "in_progress_nodes": in_progress,
            "total_nodes": len(nodes),
            "assessed_nodes": len(assessed_nodes),
            "progress_percent": round(completed / len(nodes) * 100) if nodes else 0,
        },
        "dimensions": dimensions,
        "nodes": nodes,
        "review_suggestions": review,
        "badges": _badges(student_id),
        "activity": _activity_feed(student_id),
    }


def track_node(student_id: str, node_id: str, score: float, note: str = "") -> dict[str, Any]:
    state = _read_state(student_id)
    node_state = state.setdefault("nodes", {}).setdefault(
        node_id,
        {"mastery": 0, "attempts": 0, "history": []},
    )
    attempts = int(node_state.get("attempts", 0)) + 1
    current = float(node_state.get("mastery", 0))
    score = max(0, min(100, float(score)))
    new_mastery = _update_mastery(current, score, attempts)
    now_ts = time.time()
    history = list(node_state.get("history", []))
    history.append({"score": score, "mastery": new_mastery, "note": note, "ts": now_ts})
    node_state.update(
        {
            "mastery": new_mastery,
            "attempts": attempts,
            "last_review_ts": now_ts,
            "history": history[-12:],
        }
    )
    write_json(_state_file(student_id), state)
    insert_learning_event(student_id, "knowledge_mastery", {"node_id": node_id, "score": score, "mastery": new_mastery})
    return {"node_id": node_id, "mastery": new_mastery, "attempts": attempts}


def _collect_documents(student_id: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []

    for path in sorted(COURSE_DIR.glob("*")) if COURSE_DIR.exists() else []:
        if not path.is_file():
            continue
        text = _read_text(path)
        if not text:
            continue
        docs.append(_doc_item(path=path, text=text, source_type="course_material"))

    for path in sorted(SAMPLE_DIR.glob("*.md")) if SAMPLE_DIR.exists() else []:
        text = _read_text(path)
        if text:
            docs.append(_doc_item(path=path, text=text, source_type="sample_resource"))

    for path in sorted(PATH_OUTPUT_DIR.glob("*")) if PATH_OUTPUT_DIR.exists() else []:
        if path.suffix.lower() not in {".md", ".json"}:
            continue
        text = _read_text(path)
        if text:
            docs.append(_doc_item(path=path, text=text, source_type="path_output"))

    for resource in list_resources(student_id):
        p = settings.data_path / str(resource.get("content_uri", ""))
        text = _read_text(p)
        if not text:
            continue
        docs.append(
            {
                "id": f"resource:{resource.get('id')}",
                "title": resource.get("title") or p.stem,
                "source_type": "generated_resource",
                "resource_type": resource.get("type", ""),
                "path": str(p),
                "text": text,
                "tags": resource.get("tags", []),
                "tokens": _tokenize((resource.get("title") or "") + "\n" + text),
            }
        )

    return docs


def _doc_item(path: Path, text: str, source_type: str) -> dict[str, Any]:
    title = path.stem.replace("_", " ")
    return {
        "id": f"{source_type}:{path.name}",
        "title": title,
        "source_type": source_type,
        "resource_type": "",
        "path": str(path),
        "text": text,
        "tags": _guess_tags(title + "\n" + text),
        "tokens": _tokenize(title + "\n" + text),
    }


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return _read_text_cached(str(path), path.stat().st_mtime)
    except Exception:
        return ""


@lru_cache(maxsize=256)
def _read_text_cached(path_str: str, mtime: float) -> str:
    path = Path(path_str)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _read_docx(path)
    if suffix in {".md", ".txt", ".json"}:
        for enc in ("utf-8", "gbk", "gb2312"):
            try:
                return path.read_text(encoding=enc)[:12000]
            except UnicodeDecodeError:
                continue
    return ""


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    texts = [node.text for node in root.iter() if node.tag.endswith("}t") and node.text]
    # Converted textbooks often spend the first several thousand characters
    # on publishing metadata.  A larger bounded sample reaches real chapter
    # content while keeping graph construction predictable.
    return "\n".join(texts)[:240000]


def _tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    raw = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", text)
    tokens: list[str] = []
    for item in raw:
        if re.fullmatch(r"[\u4e00-\u9fff]+", item):
            if len(item) <= 8:
                tokens.append(item)
            tokens.extend(item[i : i + 2] for i in range(max(0, len(item) - 1)))
        else:
            tokens.append(item)
    return [t for t in tokens if len(t) >= 2]


def _cosine(a: Counter, b: Counter) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _excerpt(text: str, q_tokens: list[str]) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return ""
    positions = [clean.find(t) for t in q_tokens if clean.find(t) >= 0]
    pos = min(positions) if positions else 0
    start = max(0, pos - 90)
    end = min(len(clean), pos + 260)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(clean) else ""
    return prefix + clean[start:end] + suffix


def _guess_tags(text: str) -> list[str]:
    candidates = [
        "需求分析",
        "用例建模",
        "非功能需求",
        "软件工程",
        "Python",
        "机器学习",
        "数据结构",
        "操作系统",
        "数据库",
        "Web前端",
        "嵌入式",
        "区块链",
    ]
    tags = [c for c in candidates if c.lower() in text.lower()]
    return tags[:5]


def _state_file(student_id: str) -> Path:
    return get_user_dir(student_id) / "knowledge_state.json"


def _read_state(student_id: str) -> dict[str, Any]:
    return read_json(_state_file(student_id), {"nodes": {}})


def _infer_node_mastery(node: dict[str, Any], resources: list[dict[str, Any]], weak_text: str, idx: int) -> float:
    base = 48 - idx * 2
    if any(k in weak_text for k in node["keywords"]):
        base -= 12
    for r in resources:
        text = " ".join([str(r.get("title", "")), " ".join(map(str, r.get("tags", []))), str(r.get("type", ""))])
        if any(k in text for k in node["keywords"]):
            base += 10
    return max(20, min(78, base))


def _node_status(mastery: float, idx: int) -> str:
    if mastery >= 80:
        return "completed"
    if mastery >= 55:
        return "in_progress"
    if idx <= 2 or mastery >= 40:
        return "available"
    return "locked"


def _decayed_mastery(mastery: float, last_review_ts: float, now_ts: float) -> float:
    days = max(0.0, (now_ts - last_review_ts) / 86400)
    return round(max(10, mastery * math.exp(-0.08 * days)), 1)


def _update_mastery(current: float, score: float, attempt: int) -> float:
    factor = 1.0 / (1 + 0.18 * max(0, attempt - 1))
    if score >= current:
        value = current * 0.35 + score * 0.65 * factor
    else:
        value = current * 0.78 + score * 0.22
    return round(max(0, min(100, value)), 1)


def _dimension_scores(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = {}
    for node in nodes:
        grouped.setdefault(node["layer"], []).append(float(node["current_mastery"]))
    return [
        {"label": label, "value": round(sum(values) / len(values), 1)}
        for label, values in grouped.items()
    ]


def _badges(student_id: str) -> list[dict[str, Any]]:
    profile = get_latest_profile_snapshot(student_id)
    resources = list_resources(student_id)
    events = get_user_events(student_id)
    usages = get_user_usages(student_id)
    resource_types = {r.get("type") for r in resources if r.get("type")}
    event_types = [e.get("event_type") for e in events]

    rules = [
        ("profile_builder", "画像建档", "完成一次对话式学习画像", bool(profile), 1 if profile else 0, 1),
        ("resource_maker", "资源生产者", "生成至少 3 个个性化资源", len(resources) >= 3, min(len(resources), 3), 3),
        ("multimodal_collector", "多模态收集", "覆盖至少 5 类资源类型", len(resource_types) >= 5, min(len(resource_types), 5), 5),
        ("path_executor", "路径执行者", "生成或更新个性化学习路径", "path_plan" in event_types, event_types.count("path_plan"), 1),
        ("active_questioner", "主动提问者", "完成一次智能辅导提问", "tutor" in event_types, event_types.count("tutor"), 1),
        ("feedback_loop", "反馈闭环", "提交 2 次资源反馈", len(usages) >= 2, min(len(usages), 2), 2),
        ("knowledge_searcher", "知识检索员", "使用课程知识库检索", "knowledge_search" in event_types, event_types.count("knowledge_search"), 1),
        ("reviewer", "复盘达人", "生成学习效果评估报告", "evaluate" in event_types, event_types.count("evaluate"), 1),
    ]
    return [
        {
            "id": rid,
            "name": name,
            "description": desc,
            "earned": earned,
            "progress": progress,
            "target": target,
        }
        for rid, name, desc, earned, progress, target in rules
    ]


def _activity_feed(student_id: str) -> list[dict[str, Any]]:
    events = get_user_events(student_id)
    usages = get_user_usages(student_id)
    resources = list_resources(student_id)
    items: list[dict[str, Any]] = []

    for e in events[-10:]:
        items.append(
            {
                "type": e.get("event_type", "event"),
                "title": _event_title(e.get("event_type", "")),
                "detail": e.get("payload", {}),
                "created_at": e.get("created_at"),
            }
        )
    for u in usages[-6:]:
        items.append(
            {
                "type": "resource_feedback",
                "title": "资源反馈",
                "detail": {"resource_id": u.get("resource_id"), "action": u.get("action")},
                "created_at": u.get("created_at"),
            }
        )
    for r in resources[:5]:
        items.append(
            {
                "type": "resource_created",
                "title": r.get("title", "资源生成"),
                "detail": {"type": r.get("type")},
                "created_at": r.get("created_at"),
            }
        )
    items.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return items[:12]


def _event_title(event_type: str) -> str:
    mapping = {
        "profile_update": "学习画像更新",
        "clarify": "需求澄清",
        "generate": "资源生成",
        "path_plan": "路径规划",
        "push_feedback": "推送反馈",
        "tutor": "智能辅导",
        "evaluate": "效果评估",
        "knowledge_search": "知识库检索",
        "knowledge_mastery": "掌握度更新",
    }
    return mapping.get(event_type, event_type or "学习事件")


def record_search_event(student_id: str, query: str, count: int) -> None:
    insert_learning_event(
        student_id,
        "knowledge_search",
        {"query": query[:120], "result_count": count, "created_at": datetime.now(timezone.utc).isoformat()},
    )
