import re, time, json, logging, hashlib, base64, asyncio

from coroweb import get, post
from aiohttp import web

from models import User, Comment, Blog, next_id

from config import configs

from apis import Page, APIValueError, APIResourceNotFoundError, APIError
import markdown2

logging.basicConfig(level=logging.DEBUG)

# email的匹配正则表达式
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
# 密码的匹配正则表达式
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret


# 检测当前用户是不是admin用户
def check_admin(request):
	if request.__user__ is None or not request.__user__.admin:
		raise APIPermissionError()


# 获取页数，主要是做一些容错处理
def get_page_index(page_str):
	p = 1
	try:
		p = int(page_str)
	except ValueError as e:
		print(e)
	if p < 1:
		p = 1
	return p


# 把存文本文件转为html格式的文本
def text2html(text):
	lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'),
				filter(lambda s: s.strip() != '', text.split('\n')))
	return ''.join(lines)


# 根据用户信息拼接一个cookie字符串
def user2cookie(user, max_age):
	# build cookie string by: id-expires-sha1
	# 过期时间是当前时间+设置的有效时间
	expires = str(int(time.time() + max_age))
	# 构建cookie存储的信息字符串
	s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
	L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
	# 用-隔开，返回
	return '-'.join(L)


# 根据cookie字符串，解析出用户信息相关的
@asyncio.coroutine
def cookie2user(cookie_str):
	# cookie_str是空则返回
	if not cookie_str:
		return None
	try:
		# 通过'-'分割字符串
		L = cookie_str.split('-')
		# 如果不是3个元素的话，与我们当初构造sha1字符串时不符，返回None
		if len(L) != 3:
			return None
		# 分别获取到用户id，过期时间和sha1字符串
		uid, expires, sha1 = L
		# 如果超时，返回None
		if int(expires) < time.time():
			return None
		# 根据用户id查找库，对比有没有该用户
		user = yield from User.find(uid)
		# 没有该用户返回None
		if user is None:
			return None
		# 根据查到的user的数据构造一个校验sha1字符串
		s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
		# 比较cookie里的sha1和校验sha1，一样的话，说明当前请求的用户是合法的
		if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
			logging.info('invalid sha1')
			return None
		user.passwd = '******'
		# 返回合法的user
		return user
	except Exception as e:
		logging.exception(e)
		return None




# ------------------------------------Day 7-编写 MVC---------------------------------------
# '__template__'指定的模板文件是 test.html，其他参数是传递给模板的数据，所以我们在模板的根目录 templates 下创建 test.html：
# 显示所有的用户
@get('/show_all_users')
def show_all_users():
	users = yield from User.findAll()
	logging.info('to index...')
	# return (404, 'not found')
	# 得到users数据传递给test.html显示
	return {'__template__': 'test.html', 'users': users}

# ------------------------------------Day 8-构建前端---------------------------------------
# @get('/')
# def index(request):
# 	summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
# 	blogs = [
# 		Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
# 		Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
# 		Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
# 	]
# 	return {
# 		'__template__': 'blogs.html', # 把首页改造一下，从__base__.html继承一个blogs.html
# 		'blogs': blogs
# 	}

# 首页，会显示博客列表
@get('/')
def index(*, page='1'):
	# 获取到要展示的博客页数是第几页
	page_index = get_page_index(page)
	# 查找博客表里的条目数
	num = yield from Blog.findNumber('count(id)')
	# 通过Page类来计算当前页的相关信息
	page = Page(num, page_index)
	# 如果表里没有条目，则不需要系那是
	if num == 0:
		blogs = []
	else:
		# 否则，根据计算出来的offset(取的初始条目index)和limit(取的条数)，来取出条目
		blogs = yield from Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
	# 把首页改造一下，从__base__.html继承一个blogs.shtml
	# blogs.html中使用blogs数据，没有js对象
	return {'__template__': 'blogs.html',
			'page': page,
			'blogs': blogs}


# ------------------------------------Day 9-编写API,返回所有的用户信息---------------------------------------
# 返回所有的用户信息
# @get('/api/users')
# def api_get_users(*, page='1'):
# 	page_index = get_page_index(page)
# 	num = yield from User.findNumber('count(id)')
# 	p = Page(num, page_index)
# 	if num == 0:
# 		return dict(page=p, users=())
# 	users = yield from User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
# 	for u in users:
# 		u.passwd = '******'
# 	# 只要返回一个 dict，后续的 response 这个 middleware 就可以把结果序列化为 JSON 并返回
# 	return dict(page=p, users=users)

# 返回所有的用户信息
# @get('/api/users')
# def api_get_users(request):
# 	users = yield from User.findAll(orderBy='created_at desc')
# 	logging.info('users = %s and type = %s' % (users, type(users)))
# 	for u in users:
# 		u.passwd = '******'
# 	return dict(users=users)

# ------------------------------------Day 10 - 用户注册和登录---------------------------------------
# 注册页面
@get('/register')
def register():
	# 创建一个注册页面，让用户填写注册表单，然后，提交数据到注册用户的API
	return {'__template__': 'register.html'}


# 注册请求
@post('/api/register') # 无法直接响应，通过register.html触发
def api_register_user(*, email, name, passwd):
	# 判断name是否存在，且是否只是'\n', '\r',  '\t',  ' '，这种特殊字符
	if not name or not name.strip():
		raise APIValueError('name')
	# 判断email是否存在，且是否符合规定的正则表达式
	if not email or not _RE_EMAIL.match(email):
		raise APIValueError('email')
	# 判断passwd是否存在，且是否符合规定的正则表达式
	if not passwd or not _RE_SHA1.match(passwd):
		raise APIValueError('passwd')

	# 查一下库里是否有相同的email地址，如果有的话提示用户email已经被注册过
	users = yield from User.findAll('email=?', [email])
	if len(users) > 0:
		raise APIError('register:failed', 'email', 'Email is already in use.')

	# 生成一个当前要注册用户的唯一uid
	uid = next_id()
	# 构建shal_passwd
	sha1_passwd = '%s:%s' % (uid, passwd)

	admin = False
	if email == 'admin@163.com':
		admin = True

	# 创建一个用户（密码是通过sha1加密保存）
	user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),
				image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest(),
				admin=admin)

	# 保存这个用户到数据库用户表
	yield from user.save()
	logging.info('save user OK')
	# 构建返回信息
	r = web.Response()
	# 添加cookie
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	# 只把要返回的实例的密码改成'******'，库里的密码依然是正确的，以保证真实的密码不会因返回而暴漏
	user.passwd = '******'
	# 返回的是json数据，所以设置content-type为json的
	r.content_type = 'application/json'
	# 把对象转换成json格式返回
	r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
	return r


# 登陆页面
@get('/signin')
def signin():
	# 创建一个登录页面
	return {'__template__': 'signin.html'}

# 登陆请求
@post('/api/authenticate') # /signin响应的signin.html触发/api/authenticate
def authenticate(*, email, passwd):
	# 如果email或passwd为空，都说明有错误
	if not email:
		raise APIValueError('email', 'Invalid email')
	if not passwd:
		raise APIValueError('passwd', 'Invalid  passwd')
	# 根据email在库里查找匹配的用户
	users = yield from User.findAll('email=?', [email])
	# 没找到用户，返回用户不存在
	if len(users) == 0:
		raise APIValueError('email', 'email not exist')
	# 取第一个查到用户，理论上就一个
	user = users[0]
	# 按存储密码的方式获取出请求传入的密码字段的sha1值
	sha1 = hashlib.sha1()
	sha1.update(user.id.encode('utf-8'))
	sha1.update(b':')
	sha1.update(passwd.encode('utf-8'))
	# 和库里的密码字段的值作比较，一样的话认证成功，不一样的话，认证失败
	if user.passwd != sha1.hexdigest():
		raise APIValueError('passwd', 'Invalid passwd')
	# 构建返回信息
	r = web.Response()
	# 添加cookie
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	# 只把要返回的实例的密码改成'******'，库里的密码依然是正确的，以保证真实的密码不会因返回而暴漏
	user.passwd = '******'
	# 返回的是json数据，所以设置content-type为json的
	r.content_type = 'application/json'
	# 把对象转换成json格式返回
	r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
	return r


# 登出操作
@get('/signout')
def signout(request):
	referer = request.headers.get('Referer')
	r = web.HTTPFound(referer or '/')
	# 清理掉cookie得用户信息数据
	r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
	logging.info('user signed out')
	return r




# ------------------------------------Day 12 - 管理日志列表页 http://localhost:9000/manage/blogs---------------------------------------

# 博客管理页面
@get('/manage/blogs')
def manage_blogs(*, page='1'):
	# /manage/comments	管理评论
	# /manage/users		管理用户
	# /manage/blogs/create	day 11 编写日志创建页
	# '/manage/blogs/edit?id=' + blog.id	未写(编辑博客)
	# '/api/blogs/' + blog.id + '/delete	未写(删除博客)
	# /blog/'+blog.id 进入某条博客
	# /user/'+blog.user_id					未写()
	# /api/blogs	获取所有博客信息
	return {'__template__': 'manage_blogs.html',
			'page_index': get_page_index(page)} # 诸如page_inde的值是要传递到manage_blogs.html中的


# ------------Day 11 - 编写日志创建页---------------------------------------
# 写博客页面
@get('/manage/blogs/create')
def manage_create_blog():
	# manage_blog_edit.html中调用/api/blogs
	return {'__template__': 'manage_blog_edit.html',
			'id': '',
			'action': '/api/blogs'}


# REST API，用于创建一个 Blog
@post('/api/blogs')
def api_create_blog(request, *, name, summary, content):
	# 只有管理员可以写博客
	check_admin(request)
	# name，summary,content 不能为空
	if not name or not name.strip():
		raise APIValueError('name', 'name cannot be empty')
	if not summary or not summary.strip():
		raise APIValueError('summary', 'summary cannot be empty')
	if not content or not content.strip():
		raise APIValueError('content', 'content cannot be empty')

	# 根据传入的信息，构建一条博客数据
	blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image,
				name=name.strip(), summary=summary.strip(), content=content.strip())
	# 保存
	yield from blog.save()
	return blog

# ------------end Day 11 - 编写日志创建页---------------------------------------

# eliefly fix edit&delete blog
# @post('/manage/blogs/edit?id={id}')
# def edit_blog():
#   # check_admin(request)
#   # blog = yield from Blog.find(id)
#   return {'__template__': 'manage_blog_edit.html',
#           'id': '',
#           'action': '/api/blogs'}


# 编辑已有的博客页面，与建立博客/manage/blogs/create对比
@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
	return {'__template__': 'manage_blog_edit.html',
			'id': id,
			'action': '/api/blogs/%s' % id}

# 修改日志
@post('/api/blogs/{id}')
def api_update_blog(id, request, *, name, summary, content):
	check_admin(request)
	blog = yield from Blog.find(id)
	if not name or not name.strip():
		raise APIValueError('name', 'name cannot be empty.')
	if not summary or not summary.strip():
		raise APIValueError('summary', 'summary cannot be empty.')
	if not content or not content.strip():
		raise APIValueError('content', 'content cannot be empty.')
	blog.name = name.strip()
	blog.summary = summary.strip()
	blog.content = content.strip()
	yield from blog.update()
	return blog


# eliefly 删除某个博客
# @post('/api/blogs/{id}/delete')
# def api_delete_blog(id, request):
#   logging.info(id)
#   # 先检查是否是管理员操作，只有管理员才有删除评论权限
#   check_admin(request)
#   # 查询一下评论id是否有对应的评论
#   c = yield from Blog.find(id)
#   # 没有的话抛出错误
#   if c is None:
#       raise APIResourceNotFoundError('Blog')
#   # 有的话删除
#   yield from c.remove()
#   return dict(id=id)


@post('/api/blogs/{id}/delete')
def api_delete_blog(request, *, id):
	check_admin(request)
	blog = yield from Blog.find(id)
	yield from blog.remove()
	return dict(id=id)



# ---------------------------------进入某条博客---------------------------------
# 日志详情页
@get('/blog/{id}')
def get_blog(id):
	# 根据博客id查询该博客信息
	blog = yield from Blog.find(id)
	# 根据博客id查询该条博客的评论
	comments = yield from Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
	# markdown2是个扩展模块，这里把博客正文和评论套入到markdonw2中
	for c in comments:
		c.html_content = text2html(c.content)
	blog.html_content = markdown2.markdown(blog.content)
	# 返回页面
	# /api/blogs/{{ blog.id }}/comments
	return {'__template__': 'blog.html',
			'blog': blog,
			'comments': comments}

# 对某个博客发表评论
@post('/api/blogs/{id}/comments')
def api_create_comment(id, request, *, content):
	user = request.__user__
	# 必须为登陆状态下，评论
	if user is None:
		raise APIPermissionError('content')
	# 评论不能为空
	if not content or not content.strip():
		raise APIValueError('content')
	# 查询一下博客id是否有对应的博客
	blog = yield from Blog.find(id)
	# 没有的话抛出错误
	if blog is None:
		raise APIResourceNotFoundError('Blog')
	# 构建一条评论数据
	comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image,
					  content=content.strip())
	# 保存到评论表里
	yield from comment.save()
	return comment

# ---------------------------------end 进入某条博客---------------------------------


# 获取所有博客信息
@get('/api/blogs')
def api_blogs(*, page='1'):
	page_index = get_page_index(page)
	num = yield from Blog.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page=p, blogs=())
	blogs = yield from Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	return dict(page=p, blogs=blogs)

# ---------------------------------用户管理页面 http://localhost:9000/manage/users---------------------------------
@get('/manage/users')
def manage_users(*, page='1'):
	# manage_users.html 中js调用/api/users
	return {'__template__': 'manage_users.html',
			'page_index': get_page_index(page)}

# --Day 9-编写API,返回所有的用户信息---
@get('/api/users')
def api_get_users(*, page='1'):
	page_index = get_page_index(page)
	num = yield from User.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page=p, users=())
	users = yield from User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	for u in users:
		u.passwd = '******'
	# 只要返回一个 dict，后续的 response 这个 middleware 就可以把结果序列化为 JSON 并返回
	return dict(page=p, users=users)

# ---------------------------------end 用户管理页面---------------------------------


# ---------------------------------管理评论页面 http://localhost:9000/manage/comments---------------------------------
@get('/manage/comments')
def manage_comments(*, page='1'):
	# manage_comments.html调用：
	# /api/comments
	# /api/comments/' + comment.id + '/delete'
	return {'__template__': 'manage_comments.html',
			'page_index': get_page_index(page)}

# 根据page获取评论，注释可参考 index 函数的注释，不细写了
@get('/api/comments')
def api_comments(*, page='1'):
	page_index = get_page_index(page)
	num = yield from Comment.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page=p, comments=())
	comments = yield from Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	return dict(page=p, comments=comments)

# 删除某个评论
@post('/api/comments/{id}/delete')
def api_delete_comments(id, request):
	logging.info(id)
	# 先检查是否是管理员操作，只有管理员才有删除评论权限
	check_admin(request)
	# 查询一下评论id是否有对应的评论
	c = yield from Comment.find(id)
	# 没有的话抛出错误
	if c is None:
		raise APIResourceNotFoundError('Comment')
	# 有的话删除
	yield from c.remove()
	return dict(id=id)
# ---------------------------------end 管理评论页面---------------------------------



# 管理页面
@get('/manage/')
def manage():
	return 'redirect:/manage/comments'

# 获取某条博客的信息
@get('/api/blogs/{id}')
def api_get_blog(*, id):
	blog = yield from Blog.find(id)
	return blog









