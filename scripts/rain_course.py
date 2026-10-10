"""Read the catalog already rendered in the school's Rain Classroom page."""
import re
from urllib.parse import urljoin, urlparse


def parse_rain_url(url):
    parsed = urlparse(url)
    if not (parsed.hostname == 'yuketang.cn' or (parsed.hostname or '').endswith('.yuketang.cn')):
        return None
    match = re.match(r'^/(?:pro/)?lms/([^/]+)/(\d+)(?:/|$)', parsed.path)
    if not match:
        return None
    return {'platform': 'yuketang', 'host': parsed.hostname,
            'sign': match[1], 'classroomid': match[2]}


def find_catalog(browser, target_url):
    target = parse_rain_url(target_url)
    if not target:
        raise ValueError('课程地址不是受支持的雨课堂目录地址。')
    for context in browser.contexts:
        for page in context.pages:
            parsed = parse_rain_url(page.url)
            if (parsed and parsed['host'] == target['host']
                    and parsed['classroomid'] == target['classroomid']
                    and parsed['sign'] == target['sign']
                    and urlparse(page.url).path.endswith('/studycontent')):
                return page
    raise RuntimeError('请在专用浏览器中登录并打开配置中的课程目录页面。')


def extract_catalog(page):
    result = page.evaluate('''() => {
        const root = document.querySelector('#app')?.__vue__;
        if (!root) return {error:'没有找到此版本的课程应用'};
        const components=[], seen=new Set();
        function walk(v) {
            if (!v || seen.has(v)) return;
            seen.add(v); components.push(v); (v.$children||[]).forEach(walk);
        }
        walk(root);
        const catalog=components.find(v=>Array.isArray(v.$data?.origin_chapter_list));
        if (!catalog) return {error:'课程目录未加载，请确认已登录并等待目录显示'};
        const shell=components.find(v=>v.$data?.classInfo?.course_id);
        const leafComponents=new Map(components.filter(v=>v.$props?.leafData?.id != null)
            .map(v=>[String(v.$props.leafData.id),v]));
        const routeNames={0:'lms-video',3:'lms-graph',4:'lms-forum',5:'lms-exam',6:'studycontentHomework'};
        const tasks=[];
        function collect(node,chapterName,sectionName) {
            if (!node || typeof node!=='object') return;
            if (Array.isArray(node)) {node.forEach(v=>collect(v,chapterName,sectionName));return;}
            if (node.leaf_type != null) {
                const vm=leafComponents.get(String(node.id));
                const params={classroom_id:catalog.classroom_id,sign:catalog.sign,
                    leaf_id:node.id,sku_id:vm?.skuId||0,courseware_id:0};
                const routeName=routeNames[node.leaf_type];
                const status=typeof vm?.content==='string'?vm.content:'';
                const match=status.match(/(?:^|[^0-9])([0-9]+(?:\\.[0-9]+)?)%/);
                const progress=match?Number(match[1]):null;
                tasks.push({id:node.id,type:node.leaf_type,
                    name:node.name==='Video'&&sectionName?sectionName:node.name,
                    chapter:chapterName,locked:node.is_locked===true,
                    visible:node.is_show!==false,status,progress,
                    completed:progress!==null&&progress>=100,
                    path:routeName?root.$router.resolve({name:routeName,params}).href:null});
                return;
            }
            if (Array.isArray(node.section_leaf_list)) {
                node.section_leaf_list.forEach(v=>collect(v,node.name||chapterName,''));
            } else if (Array.isArray(node.leaf_list)) {
                node.leaf_list.forEach(v=>collect(v,chapterName,node.name||sectionName));
            }
        }
        collect(catalog.$data.origin_chapter_list,'','');
        return {course_id:shell?.$data.classInfo.course_id,
            course_name:shell?.$data.classInfo.course_name,
            classroomid:catalog.classroom_id,sign:catalog.sign,tasks};
    }''')
    if result.get('error'):
        raise RuntimeError(result['error'])
    if not result.get('course_id') or not result.get('tasks'):
        raise RuntimeError('未读到课程编号或任务目录，请等待页面加载完成后重试。')
    prefix = f"/pro/lms/{result['sign']}/{result['classroomid']}/"
    host = urlparse(page.url).hostname
    for task in result['tasks']:
        if task.get('path'):
            parsed = urlparse(urljoin(page.url, task['path']))
            if parsed.hostname != host or not parsed.path.startswith(prefix):
                raise RuntimeError('目录中的任务网址与目标课堂不一致，已停止。')
    return result
