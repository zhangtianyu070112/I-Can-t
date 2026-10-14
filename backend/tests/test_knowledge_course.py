from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services import knowledge_hub as hub


class KnowledgeCourseTest(unittest.TestCase):
    def test_markdown_chapters_keep_subsections_and_ignore_book_heading(self):
        body = '# 教材\n\n## 第一章 用例\n' + '参与者与用例图共同描述系统行为。' * 6
        body += '\n### 练习\n解释参与者的作用。\n## 第二章 验证\n' + '验收标准与需求追踪用于验证需求。' * 6
        chapters = hub._build_uploaded_textbook_chapters(body, '教材')
        self.assertEqual([c['chapter_title'] for c in chapters], ['第一章 用例', '第二章 验证'])
        self.assertIn('参与者', chapters[0]['keywords'])
        self.assertIn('需求追踪', chapters[1]['keywords'])

    def test_plain_numbered_chapters_under_markdown_title(self):
        body = '# 教材\n\n第一章 基础\n' + '需求分析明确系统范围。' * 6
        body += '\n第二章 验证\n' + '验收标准记录验证条件。' * 6
        self.assertEqual(len(hub._build_uploaded_textbook_chapters(body, '教材')), 2)

    def test_demo_graph_has_traceable_course_content_and_is_not_given_to_new_learners(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(settings, 'data_dir', temp), \
             patch.object(hub, 'CHAPTER_KNOWLEDGE_DIR', Path(temp) / 'uploads'), \
             patch.object(hub, 'COURSE_DIR', Path(temp) / 'courses'):
            graph = hub.graph_data('demo', max_nodes=100)
            self.assertEqual(graph['stats']['chapters'], 6)
            self.assertGreaterEqual(graph['stats']['concepts'], 18)
            self.assertIn('预置演示讲义', graph['course_summary'])
            source = (hub.PROJECT_ROOT / 'roadshow-data/courses/requirements-modeling.md').read_text(encoding='utf-8')
            for node in graph['nodes']:
                self.assertIn(node['name'], source)
                self.assertNotRegex(node['name'], r'[a-f0-9]{16}')
            self.assertEqual(hub.graph_data('new-learner')['nodes'], [])
