#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This script copies entries from a CSDN blog to an other weblog, using the MetaWeblog API.
It can move both posts and comments.
Require 'BeautifulSoup' module
Released under the GPL. Report bugs to davelv@qq.com
Thanks for ordinary author Wei Wei(live space mover)
(C) Davelv, homepage http://www.davelv.net
(C) Wei Wei,homepage: http://www.broom9.com
General Public License: http://www.gnu.org/copyleft/gpl.html
Last modified 2012-01-02 08:21
"""

__VERSION__ = "1.0"
__PROGRAM__ = "CsdnBlogMover"
import sys
import os
import codecs
import httplib
import urllib2
from BeautifulSoup import BeautifulSoup
import re
import logging
from datetime import date, datetime, timedelta
import time
from optparse import OptionParser
from string import Template
import pickle
from xml.sax import saxutils
import json

commentIdList = {}
categories = set([])

csdnDatetimePattern = u'%Y-%m-%d %H:%M';
csdnHost = u'blog.csdn.net'
csdnCommentsPre = u''
http = httplib.HTTPConnection(csdnHost)

    
def GetPage(url, retryTimes=5, retryIntvl=3):
    global http
    userAgent = {u'User-Agent':u'Mozilla/5.0 (X11; Linux i686; rv:8.0) Gecko/20100101 Firefox/8.0',
                 u'Connection': u'keep-alive'}
    while retryTimes>0:
        try:
            http.request("GET", url, headers=userAgent)
            return http.getresponse()
        except httplib.CannotSendRequest:
            logging.warning("Fetch data failure, reconnect after %ds", retryIntvl)
            http.close()
        except:
            logging.warning("Fetch data failure, retry after %ds", retryIntvl)
        finally:
            retryTimes -=1
            if retryTimes == 0:
                raise
            time.sleep(retryIntvl)

        
def PrettyCode(content):
    """
    Pretty code area in article content use pre to replace textarea
    working...
    """
    textarea = re.compile(u'<textarea.+?name="code".+?class="([^"]+)">(.+?)</textarea>', re.S)
    return  textarea.sub(u'<pre class="\g<1>">\g<2></pre>', content)
def PrettyComment(comment):
    quote = re.compile(u'^\[quote=([^\]]+)\](.+)\[/quote\]', re.S)
    comment = quote.sub(u'<fieldset><legend>引用 \g<1>:</legend>\g<2></fieldset>', comment)
    reply = re.compile(u'\[reply\]([^\[]+)\[/reply\]')
    return reply.sub(u'回复 \g<1>:', comment)
        
def ParseCommentDate(dateStr):
  #"""
  #Parse date string in comments
  #examples:
  #刚刚
  #11分钟前
  #11小时前
  #昨天 11:11
  #前天 11:11
  #3天前 11:11
  #2011-11-11 11:11
  #"""
  datetimeNow = datetime.today()  
  reg_method = {
    u'\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}':lambda m:datetime.strptime(m.group(0), csdnDatetimePattern),
    u'(\d)天前 (\d{1,2}):(\d{1,2})': lambda m: datetimeNow.replace(hour=int(m.group(2)), minute=int(m.group(3))) - timedelta(days=int(m.group(1))),
    u'前天 (\d{1,2}):(\d{1,2})': lambda m:datetimeNow.replace(hour=int(m.group(1)), minute=int(m.group(2))) - timedelta(days=2),
    u'昨天 (\d{1,2}):(\d{1,2})': lambda m:datetimeNow.replace(hour=int(m.group(1)), minute=int(m.group(2))) - timedelta(days=1),
    u'(\d{1,2})小时前': lambda m: datetimeNow - timedelta(hours=int(m.group(1))),
    u'(\d{1,2})分钟前': lambda m: datetimeNow - timedelta(minutes=int(m.group(1))),
    u'刚刚': lambda m: datetimeNow }
  for k, v in reg_method.items() :
    m = re.search(k, dateStr)
    if m :
      return v(m)

def FetchEntry(url, datetimePattern='%Y-%m-%d %H:%M', postOnly=False):
    """
    Structure of entry
    entry
    |-title
    |-manage
    |   |-category (maybe NULL)
    |   |-date
    |   |-view' counts
    |   |-comments' counts
    |-content
    |-permalLink (permalLink of previous entry, may be NULL)
    |-comments
        |-email
        |-author
        |-comment
        |-date
    """
    temp = url.split('/')
    articleID = temp[-1]
    logging.debug("Fetch article page from %s",url)
    soup = BeautifulSoup(GetPage(url))    #logging.debug("Got Page Content\n---------------\n%s",soup.prettify())
    item = {'title':'', 'date':'', 'views':'', 'content':'', 'category':[], 'prevLink':'', 'id':articleID, 'comments':[]}
    #find article
    article = soup.find(id="article_details")
    if article :
        logging.debug("Found article")
    else :
        logging.debug("Can't found article")
        sys.exit(2)
    #title
    temp = article.find(attrs={"class":"article_title"}).find(attrs={"class":"link_title"}).find('a')
    if temp :
        item['title'] = u'' + temp.contents[0].string
        logging.debug("Found title %s", item['title'])
    else :
        logging.warning("Can't find title")
        sys.exit(2)
    #category / date / view times / comments times
    manage = article.find(attrs={"class":"article_manage"})
    #category
    temp = manage.find(attrs={"class":"link_categories"})
    if temp :
       item['category'] = map(lambda a: u''+a.text, temp.findAll('a'))
       categoryStr = u''
       for cate in item['category'] : categoryStr+=cate+u', '
       logging.debug("Found category %s",categoryStr[:-2])
       global categories
       categories.update(item['category'])
    else:
        logging.debug("No category, use default")
    #date
    temp = manage.find(attrs={"class":"link_postdate"})
    if temp :
        item['date'] = u'' + temp.contents[0].string
        item['date'] = datetime.strptime(item['date'], datetimePattern)
        logging.debug("Found date %s", item['date'])
    else :
        logging.warning("Can't find date")
        sys.exit(2)
    #views
    temp = manage.find(attrs={"class":"link_view"})
    if temp :
        item['views'] = int (temp.contents[0][0:-3])
        logging.debug("Found views count %d", item['views'])
    else :
        logging.warning("Can't find views count")
        sys.exit(2)
    #comments count
    temp = manage.find(attrs={"class":"link_comments"})
    comments_cnt = 0
    if temp :
        comments_cnt = int(temp.contents[1][1:-1])
        logging.debug("Found comments count %d", comments_cnt)
    else :
        logging.warning("Can't find comments count")
        sys.exit(2)
    #content
    temp = article.find(id="article_content") or article.find(attrs={"class":"article_content"})
    if temp :
        item['content'] = PrettyCode(u''.join(map(unicode, temp.contents)))
        logging.debug("Found content");
    else:
        logging.warning("Can't find content")
    
    #previous entry link
    temp = article.find('li', attrs={'class':'prev_article'});
    if temp:
        item['prevLink'] = u'' + temp.find('a')['href']
        logging.debug("Found previous permaLink %s", item['prevLink'])
    #comments get from server
    if postOnly or comments_cnt == 0:
        return item
    commentsURL = csdnCommentsPre + articleID
    logging.debug("Fetch comments from %s", commentsURL)
    page = GetPage(commentsURL) 
    #OMG, when I write out the parse functon by using regex
    #I found it can be solved by json ulity in one line!!! 
    #{"list":[{"ArticleId":7079224,"BlogId":66847,"CommentId":2065153,"Content":"XXXX","ParentId":0,"PostTime":"昨天 11:26","Replies":null,"UserName":"evilhacker","Userface":"http://xxx.jpg"},...],...}
    item['comments'] = json.load(page)['list']


    if item['comments'] == None:
        logging.warning("Can't find conments")
    for v in item['comments']:
        uselessPriorities = ['ArticleId','BlogId','Replies', 'Userface']
        for i in uselessPriorities: del v[i]
        v['PostTime'] = ParseCommentDate(v['PostTime'])
        v['Content'] = PrettyComment(v['Content'])
        
    return item

def FetchBlogInfo(url ,needPermaLink = True):
    global csdnCommentsPre
    blogInfo = {}
    logging.info("connectiong to web page %s", url)
    soup = BeautifulSoup(GetPage(url))
    blogInfo['user'] = u''+re.search(csdnHost+"/([^/]+)", url).group(1)
    blogInfo['blogURL'] = u'http://'+csdnHost+'/'+blogInfo['user']+'/'
    csdnCommentsPre = blogInfo['blogURL']+ "comment/list/"
    logging.info('Blog URL is %s', blogInfo['blogURL'])
    blogInfo['nowTime'] = u'' + datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')
    blogInfo['blogTitle'] = u'' + soup.find(id='blog_title').h1.text
    blogInfo['blogDesc'] = u'' + soup.find(id='blog_title').h2.text
    logging.debug('Blog Title is %s', blogInfo['blogTitle'])
    
    if not needPermaLink :
        blogInfo["permaLink"] = url
        return blogInfo
    
    linkNode = soup.find(attrs={"class":"link_title"}).find('a')
    if linkNode :
        #if the linkNode is like "/davelv/article/details/6191987" concat after "http://blog.csdn.net/"
        blogInfo["permaLink"] = linkNode["href"]
    else :
        logging.error("Can't find permaLink")
    return blogInfo 
            
def ExportHead(f, dic, categories=[]):
    t = Template(u"""<?xml version="1.0" encoding="UTF-8"?>
<!--
    This is a WordPress eXtended RSS file generated by Live Space Mover as an export of 
    your blog. It contains information about your blog's posts, comments, and 
    categories. You may use this file to transfer that content from one site to 
    another. This file is not intended to serve as a complete backup of your 
    blog.
    
    To import this information into a WordPress blog follow these steps:
    
    1.  Log into that blog as an administrator.
    2.  Go to Manage > Import in the blog's admin.
    3.  Choose "WordPress" from the list of importers.
    4.  Upload this file using the form provided on that page.
    5.  You will first be asked to map the authors in this export file to users 
        on the blog. For each author, you may choose to map an existing user on 
        the blog or to create a new user.
    6.  WordPress will then import each of the posts, comments, and categories 
        contained in this file onto your blog.
-->

<!-- generator="{programInfo}" created="${nowTime}"-->
<rss version="2.0"
    xmlns:excerpt="http://wordpress.org/export/1.1/excerpt/"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    xmlns:wfw="http://wellformedweb.org/CommentAPI/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:wp="http://wordpress.org/export/1.1/"
>

<channel>
    <title>${blogTitle}</title>
    <link>${blogURL}</link>
    <description>${blogDesc}</description>
    <pubDate>${nowTime}</pubDate>
    <generator>${programInfo}</generator>
    <language>zh</language>
    <wp:wxr_version>1.1</wp:wxr_version>""") #need blogTitle, nowTime, blogURL
    catT = Template(u'''
    <wp:category><wp:term_id>${categoryId}</wp:term_id><wp:category_nicename>${niceName}</wp:category_nicename><wp:category_parent/><wp:cat_name><![CDATA[${category}]]></wp:cat_name></wp:category>
    <wp:tag><wp:term_id>${tagId}</wp:term_id><wp:tag_slug>${niceName}</wp:tag_slug><wp:tag_name><![CDATA[${category}]]></wp:tag_name></wp:tag>''')
    catStr = u''
    i = -1
    for cat  in categories:
        i = i + 2
        logging.debug("Cate:%s", cat)
        catStr += catT.substitute(
        categoryId=i,
        tagId=i + 1,
        category=cat,
        niceName=urllib2.quote(cat.encode('utf-8'))
        )
    dic['blogTitle'] = saxutils.escape(dic['blogTitle'])
    dic['programInfo'] = u'' + __PROGRAM__ + __VERSION__
    f.write(t.substitute(dic))
    f.write(catStr)
 
def ExportEntry(f, entry, user):
    commentT = Template(u"""
        <wp:comment>
            <wp:comment_id>${commentId}</wp:comment_id>
            <wp:comment_author><![CDATA[${commentAuthor}]]></wp:comment_author>
            <wp:comment_author_email></wp:comment_author_email>
            <wp:comment_author_url>${authorURL}</wp:comment_author_url>
            <wp:comment_author_IP></wp:comment_author_IP>
            <wp:comment_date>${commentDate}</wp:comment_date>
            <wp:comment_date_gmt>${commentDateGMT}</wp:comment_date_gmt>
            <wp:comment_content><![CDATA[${commentContent}]]></wp:comment_content>
            <wp:comment_approved>1</wp:comment_approved>
            <wp:comment_type></wp:comment_type>
            <wp:comment_parent>${parentId}</wp:comment_parent>
        </wp:comment>""") #need commentId, commentAuthor, commentEmail, commentURL,commentDate,commentContent
    itemT = Template(u"""
    <item>
        <title>${entryTitle}</title>
        <link>${entryURL}</link>
        <pubDate>${pubDate}</pubDate>
        <dc:creator>${entryAuthor}</dc:creator>
        ${categories}
        <guid isPermaLink="false"></guid>
        <description></description>
        <content:encoded><![CDATA[${entryContent}]]></content:encoded>
        <wp:post_id>${entryId}</wp:post_id>
        <wp:post_date>${postDate}</wp:post_date>
        <wp:post_date_gmt>${postDateGMT}</wp:post_date_gmt>
        <wp:comment_status>open</wp:comment_status>
        <wp:ping_status>open</wp:ping_status>
        <wp:post_name>${postName}</wp:post_name>
        <wp:status>publish</wp:status>
        <wp:post_parent>0</wp:post_parent>
        <wp:menu_order>0</wp:menu_order>
        <wp:post_type>post</wp:post_type>
        <wp:postmeta>
            <wp:meta_key>views</wp:meta_key>
            <wp:meta_value><![CDATA[${views}]]></wp:meta_value>
        </wp:postmeta>
        ${comments}
    </item>""") #need entryTitle, entryURL, entryAuthor, category, entryContent, entryId, postDate,postDateGMT, pubDate,views
    cateT = Template(u"""
        <category domain="category" nicename="${niceName}"><![CDATA[${category}]]></category>
        <category domain="post_tag" nicename="${niceName}"><![CDATA[${category}]]></category>""")#nedd category niceName

    commentsStr = u""
    #logging.debug(entry)
    for comment in entry['comments']:
        commentsStr += commentT.substitute(
        commentId=comment['CommentId'],
            commentAuthor=saxutils.escape(comment['UserName']),
            authorURL=u'http://'+csdnHost + u'/' + saxutils.escape(comment['UserName']),
            commentDate=comment['PostTime'].strftime('%Y-%m-%d %H:%M:%S'),
            commentDateGMT=(comment['PostTime'] - timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S'),
            commentContent=comment['Content'],
            parentId=comment['ParentId'])
        #logging.debug(comment['comment'])
    #category
    categoryStr = u''
    for cate in entry['category'] :
        categoryStr += cateT.substitute(
            category=cate,
        niceName=urllib2.quote(cate.encode('utf-8')))
    #logging.debug(entry['category'])
    itemStr = itemT.substitute(
    entryTitle=saxutils.escape(entry['title']),
        entryURL='',
        entryAuthor=user,
        entryContent=entry['content'],
        postName=urllib2.quote(entry['title'].encode('utf-8')),
        entryId=entry['id'],
        postDate=entry['date'].strftime('%Y-%m-%d %H:%M:%S'),
        postDateGMT=(entry['date'] - timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S'),
        pubDate=entry['date'].strftime('%a, %d %b %Y %H:%M:%S +0800'),
        views=entry['views'],
        comments=commentsStr,
        categories=categoryStr)
    #logging.debug(itemStr)
    f.write(itemStr)
    
def ExportFoot(f):
    f.write("""
</channel>
</rss>
""")
    f.close()

def LoadCache(fileName = 'entries.cache'):
    entries = []
    if not os.path.exists(fileName):
        return entries
    logging.info('Found cache file')
    cacheFile = open(fileName, 'r')
    try:
        while True:
            entry = pickle.load(cacheFile)
            categories.update(entry['category'] )
            logging.info('Load entry from cache file with title %s', entry['title'])
            entries.append(entry) 
    except (pickle.PickleError, EOFError):
        logging.info("No more entries in cache file for loading")
    finally:
        cacheFile.close()       
    return entries
def main():
    #main procedure begin
    parser = OptionParser()
    parser.add_option("-s", "--source", action="store", type="string", dest="srcURL", help="source csdn blog address")
    parser.add_option("-b", "--begin", action="store", type="string", dest="beginURL", help="a permalink in source csdn blog address for starting with, if this is specified, source url will be ignored.")    
    parser.add_option("-l", "--limit", action="store", type="int", dest="limit", help="limit number of transfered posts, you can use this option to test")
    parser.add_option("-o", "--postonly", action="store_true", dest="postOnly", default=False, help="if postonly setted, program will only post without comments, default is False")
    (options, args) = parser.parse_args()
    
    
    #export all options variables
    for i in dir(options):
        exec '' + i + " = options." + i

    global categories
    #load cache and resume from the last post in it
    cacheName = 'entries.cache'
    entries = LoadCache(cacheName)
    
    #find blog info
    if beginURL :
        blogInfo = FetchBlogInfo(beginURL, False)
        logging.info('Start fetching from %s', beginURL)
    elif srcURL:
        blogInfo = FetchBlogInfo(srcURL, True)
        logging.info("Found permaLink %s", blogInfo["permaLink"])
    else:
        logging.error("Error, you must give either srcURL or beginURL")
        sys.exit(2)
    
    #main loop, retrieve every blog entry and post to dest blog
    count = 0
    cacheFile = open(cacheName, 'a')
    if len(entries) >0:
        permaLink = entries[-1]['prevLink']
    else :
        permaLink = blogInfo['permaLink']
    try:
        while permaLink:
            item = FetchEntry(permaLink, postOnly=postOnly)
            #
            tt=item['title']
            i=1
            for e in entries : 
                if e['title'] == item['title']: 
                    item['title']=tt + str(i)
                    i += 1
                    break
            logging.info("Got a blog entry titled %s with %d comments successfully", item['title'], len(item['comments']))
            entries.append(item)
            pickle.dump(item,cacheFile)
            cacheFile.flush()
            logging.debug("-----------------------")
            if 'prevLink' in item :
                permaLink = item['prevLink']
            else :
                break
            count += 1
            if limit and count >= limit : break
    finally:
        cacheFile.close()
    #export header

    exportFileName = 'export_' + datetime.now().strftime('%m%d%Y-%H%M') + '.xml'
    f = codecs.open(exportFileName, 'w', 'utf-8')
    if f:
        logging.info('Export XML to file %s', exportFileName)
    else:
        logging.error("Can't open export file %s for writing", exportFileName)
        sys.exit(2)
    ExportHead(f, blogInfo, categories)
    logging.debug('Exported header')
    #export entries
    for entry in entries:
        ExportEntry(f, entry, blogInfo['user'])
    #export Foot
    ExportFoot(f)
    logging.debug('Exported footer')
    #Delete cache file
    os.remove(cacheName)
    logging.info("Deleted cache file")
    logging.info("Finished! Congratulations!")

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
        format='LINE %(lineno)-4d  %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M',
        filename='blog-mover.log',
        filemode='w');
    # define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    # set a format which is simpler for console use
    formatter = logging.Formatter('LINE %(lineno)-4d : %(levelname)-8s %(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)
    try:
        main()
    except SystemExit:
        pass
    except:
        logging.exception("Unexpected error")
        raise

