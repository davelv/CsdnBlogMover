#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
This script copies entries from a live space (msn space) weblog to an other weblog, using the MetaWeblog API.
It can move both posts and comments.
Require 'BeautifulSoup' module
Released under the GPL. Report bugs to weiwei9@gmail.com

(c) Wei Wei, homepage: http://www.broom9.com
General Public License: http://www.gnu.org/copyleft/gpl.html
"""

__VERSION__="1.0"

import sys
import os
import codecs
import xmlrpclib
import urllib
import urllib2
from BeautifulSoup import BeautifulSoup,Tag,CData
import re
import logging
from datetime import date
from datetime import datetime
from datetime import timedelta
import time
from optparse import OptionParser
from string import Template
import pickle
import xml
from xml.sax import saxutils
import string

entries = []
categories = set([])
commentId = 10000
entryId = 10000
userAgent={'User-Agent':'Mozilla/5.0 (X11; Linux i686; rv:8.0) Gecko/20100101 Firefox/8.0'}
csdnDatetimePattern = '%Y-%m-%d %H:%M';
def replaceUnicodeNumbers(text):
    rx = re.compile('&#[0-9]+;')
    def one_xlat(match):
        return unichr(int(match.group(0)[2:-1]))
    return rx.sub(one_xlat, text)

def parseCommentDate(dateStr):
  #"""
  #Parse date string in comments
  #examples:
  #  刚刚
  #  11分钟前
  #  11小时前
  #  昨天 11:11
  #  前天 11:11
  #  2011-11-11 11:11
  #"""
  datetimeNow = datetime.today()  
  reg_method = {
    '\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}':lambda m:datetime.strptime(m.group(0),csdnDatetimePattern),
    '前天 (\d{1,2}):(\d{1,2})': lambda m:datetimeNow.replace(hour=int(m.group(1)), minute=int(m.group(2)))-timedelta(days=2), 
    '昨天 (\d{1,2}):(\d{1,2})': lambda m:datetimeNow.replace(hour=int(m.group(1)), minute=int(m.group(2)))-timedelta(days=1),
    '(\d{1,2})小时前': lambda m: datetimeNow-timedelta(hours=int(m.group(1))),
    '(\d{1,2})分钟前': lambda m: datetimeNow-timedelta(minutes=int(m.group(1))), 
    '刚刚': lambda m: datetimeNow }
  for k,v in reg_method.items() :
    m = re.search(k,dateStr)
    if m :
      return v(m)

  raise Exception , "Can't parse comment date string " + dateStr


def testParseCommentDate():
  test_d_strs = ["5分钟前","刚刚","4小时前","昨天 12:09发表", "前天 01:18","2011-11-11 11:11", "2000-01-01 12:00"]
  for s in test_d_strs:
    print s, parseCommentDate(s)

def fetchComments(comments, commentsCounts):
    try:
        #maybe need to fetch several pages of comments
         while commentsCounts >0:
		
            temp = comments.findAll(attrs={"class":"cc2_cmt"})  #a comment div
            if temp :
                for cmDiv in temp:
                    comment = {'email':'','author':'','comment':'','date':'','url':''} #make sure every key is in
                    #logging.debug('Comment Div content\n %s', cmDiv)
                    #the name and email element. The first page is different from latter pages, latter ones have one more "span" element
                    comment_author = cmDiv.find(attrs={"class":"cc2_dnmmain"}) # or cmDiv.find(attrs={"class":"ccName"})
                    comment['author'] = replaceUnicodeNumbers(u''.join(comment_author.findAll(text=True)))
                    comment['comment']=u''.join(map(CData,cmDiv.find(attrs={"class":"cc2_txt"}).contents))
                    comment['date']=parseCommentDate(cmDiv.findNext(attrs={"class":"cc2_tsmain"}).string, i['date']).strftime("%Y-%m-%d %H:%M:%S")
                    urlTag = cmDiv.find(attrs={"class":"cc2_dnmmain"})
                    if urlTag:
                       comment['url']=urlTag.find('a')['href']
                    i['comments'].append(comment)
            #fetch next page comments
            #for first page, find this link
            nextPageCommentATag = soup.find(id="sn_ccpgNextCommentControl")
            if nextPageCommentATag :
                needFetchComments = True
                req = urllib2.Request(nextPageCommentATag["href"])
                req.add_header('User-agent', 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.8.1.5) Gecko/20070713 Firefox/2.0.0.5')
                page = urllib2.build_opener().open(req).read()
                soup = BeautifulSoup(page)
            else :
                needFetchComments = False
        i['comments'].reverse() # bug reported by Sun Yue
        logging.debug('Got %d comments of this entry',len(i['comments']))
    except:
        logging.debug("===============Fetching Comments Error, Dump Variables================")
        logging.debug("-- cmDiv")
        logging.debug(cmDiv.prettify())        
        logging.debug("-- soup")
        logging.debug(soup.prettify())        
        logging.debug("======================================================================")
        logging.error("HTML parsing error, probably because of updating of live space, please email the log file to me: weiwei9@gmail.com")
        raise

def fetchEntry(url,datetimePattern = '%Y-%m-%d %H:%M',mode='all'):
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
    logging.debug("begin fetch page %s",url)
    req = urllib2.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux i686; rv:8.0) Gecko/20100101 Firefox/8.0')
    page = urllib2.build_opener().open(req).read()
    soup = BeautifulSoup(page)
    logging.debug("fetch page successfully")
    #logging.debug("Got Page Content\n---------------\n%s",soup.prettify())
    i={'title':'','date':'','views':'','content':'','category':'','prevLink':'','comments':[]}
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
        i['title']=temp.contents[0].string
        logging.debug("Found title %s",i['title'])
    else :
        logging.warning("Can't find title")
        sys.exit(2)
    #category / date / view times / comments times
    manage = article.find(attrs={"class":"article_manage"})
    #category
    temp = manage.find(attrs={"class":"link_categories"})
    if temp :
       i['category']=temp.find('a').contents[0].string
       logging.debug("Found category %s",i['category'])
       global categories
       categories.add(i['category'])
    else:
        logging.debug("No category")
    #date
    temp = manage.find(attrs={"class":"link_postdate"})
    if temp :
        i['date']=temp.contents[0].string
        i['date'] = datetime.strptime(i['date'],datetimePattern)
        logging.debug("Found date %s",i['date'])
    else :
        logging.warning("Can't find date")
        sys.exit(2)
    #views
    temp = manage.find(attrs={"class":"link_view"})
    if temp :
        i['views']=int (temp.contents[0][0:-3])
        logging.debug("Found views count %d",i['views'])
    else :
        logging.warning("Can't find views count")
        sys.exit(2)
    #comments count
    temp = manage.find(attrs={"class":"link_comments"}).find('a')
    if temp :
        comments_cnt = int (temp.nextSibling[1:-1])
        logging.debug("Found comments count %d",comments_cnt)
    else :
        logging.warning("Can't find comments count")
        sys.exit(2)
    #content
    temp = article.find(id="article_content") or article.find(attrs={"class":"article_content"})
    if temp :
        i['content']=u''.join(map(unicode,temp.contents))
        logging.debug("Found content");
    else:
        logging.warning("Can't find content")
    
    #previous entry link
    temp = article.find('li',attrs={'class':'prev_article'});
    if temp:
        i['prevLink'] = temp.find('a')['href']
        logging.debug("Found previous permalink %s",i['prevLink'])
    #comments
    if mode != 'postsOnly':
	temp = soup.find(id="comment_list")
	if temp:
	    i['comments'] = fetchComments(temp, comments_cnt)
	else: 
	    logging.warning("Can't find conments")
    return i

    
def getDstBlogEntryList(server, user, passw, maxPostID = 255):
    logging.info('Fetching dst blog entry list')
    pIdRange = range(1,maxPostID)
    entryDict = {}
    successCount = 0
    errorCount = 0
    for pId in pIdRange:
        try:
            entry = server.metaWeblog.getPost(pId,user,passw)
            entryDict[entry['title']]=pId
            logging.debug("Get post %s, title is %s",pId,entry['title'])
            successCount+=1
        except xmlrpclib.Fault:
            logging.debug("No post of id %s", pId)
        except xml.parsers.expat.ExpatError:
            logging.warn("Failed to retrieve Post with id %d",pId)
            errorCount+=1
    logging.info('Get %d posts successfully. %d posts failed. Check warning log to see details',successCount,errorCount)
    return entryDict
    
def publishPost(server, blogid, user, passw, wpost,published):
    i = 1
    while i<6:
        try:
            logging.debug("publishing post on new weblog (account:%s); try:%d)...",user,i)
            return server.metaWeblog.newPost(blogid,user,passw,wpost,published)
        except:
            logging.debug("error. Retrying...")
            time.sleep(3+i)
            i+=1

def find1stPermalink(srcURL):
    logging.info("connectiong to source blog %s",srcURL)
    req = urllib2.Request(srcURL, headers=userAgent)
    page = urllib2.urlopen(req)
    logging.info("connect successfully, look for 1st Permalink")
    soup = BeautifulSoup(page)
    linkNode = soup.find(attrs={"class":"link_title"}).find('a')
    if linkNode :
        #Update @ 2007-10-21
        #if the permalink is like "/davelv/article/details/6191987" concat after "http://blog.csdn.net"
        linkNodeHref = req.get_type() + "://" + req.get_host() + linkNode["href"]
    
        logging.info("Found 1st Permalink %s",linkNodeHref)
        return linkNodeHref;
    else :
        logging.error("Can't find 1st Permalink")
        return False
    
def publishComments(entry,postCommentsURL,pID=0,dstBlogEntryDict={}):
    if len(entry['comments'])>0 :
        logging.debug('Try to publish comments for post %s',entry['title'])
        if not pID:
            if dstBlogEntryDict.has_key(entry['title']):
                pID = dstBlogEntryDict[entry['title']]
            else:
                logging.warn("No pID provided, and can't find this post title in dest blog entries dict")
                return
        for c in entry['comments']:
            c["comment_post_ID"]=pID
            data = urllib.urlencode(c)
            f = urllib.urlopen(postCommentsURL,data)
            s = f.read()
            if s=='Success' : logging.debug('Post comment successfully')
            else : logging.debug('Post comment failed')
            f.close()
            
def exportHead(f,dic,categories=[]):
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

<!-- generator="Live Space Mover 1.0" created="${nowTime}"-->
<rss version="2.0"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    xmlns:wfw="http://wellformedweb.org/CommentAPI/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:wp="http://wordpress.org/export/1.0/"
>

<channel>
    <title>${blogTitle}</title>
    <link>${blogURL}</link>
    <description></description>
    <pubDate>Tue, 30 Nov 1999 00:00:00 +0000</pubDate>
    <generator>Live Space Mover 1.0</generator>
    <language>en</language>
""") #need blogTitle, nowTime, blogURL
    catT = Template(u'''<wp:category><wp:cat_name><![CDATA[${category}]]></wp:cat_name></wp:category>\n''')
    catStr = u''
    for cat in categories:
        catStr+=catT.substitute(category=cat)
    dic['blogTitle'] = saxutils.escape(dic['blogTitle'])
    f.write(t.substitute(dic))
    f.write(catStr)
    
def exportEntry(f,entry,user):
    commentT = Template(u"""<wp:comment>
<wp:comment_id>${commentId}</wp:comment_id>
<wp:comment_author>${commentAuthor}</wp:comment_author>
<wp:comment_author_email>${commentEmail}</wp:comment_author_email>
<wp:comment_author_url>${commentURL}</wp:comment_author_url>
<wp:comment_author_IP></wp:comment_author_IP>
<wp:comment_date>${commentDate}</wp:comment_date>
<wp:comment_date_gmt>0000-00-00 00:00:00</wp:comment_date_gmt>
<wp:comment_content>${commentContent}</wp:comment_content>
<wp:comment_approved>1</wp:comment_approved>
<wp:comment_type></wp:comment_type>
<wp:comment_parent>0</wp:comment_parent>
</wp:comment>""") #need commentId, commentAuthor, commentEmail, commentURL,commentDate,commentContent
    itemT = Template(u"""<item>
<title>${entryTitle}</title>
<link>${entryURL}</link>
<pubDate>${pubDate}</pubDate>
<dc:creator>${entryAuthor}</dc:creator>

        <category><![CDATA[${category}]]></category>

<guid isPermaLink="false"></guid>
<description></description>
<content:encoded><![CDATA[${entryContent}]]></content:encoded>
<wp:post_id>${entryId}</wp:post_id>
<wp:post_date>${postDate}</wp:post_date>
<wp:post_date_gmt>${postDateGMT}</wp:post_date_gmt>
<wp:comment_status>open</wp:comment_status>
<wp:ping_status>open</wp:ping_status>
<wp:post_name>${entryTitle}</wp:post_name>
<wp:status>publish</wp:status>
<wp:post_parent>0</wp:post_parent>
<wp:menu_order>0</wp:menu_order>
<wp:post_type>post</wp:post_type>
${comments}
</item>
""") #need entryTitle, entryURL, entryAuthor, category, entryContent, entryId, postDate, pubDate
    global entryId
    global commentId
    commentsStr = u""
    #logging.debug(entry)
    for comment in entry['comments']:
        commentsStr+=commentT.substitute(commentId = commentId,
            commentAuthor = saxutils.escape(comment['author']),
            commentEmail = saxutils.escape(comment['email']),
            commentURL = comment['url'],
            commentDate=comment['date'],
            commentContent=comment['comment'])
        commentId-=1
        #logging.debug(comment['comment'])
    #logging.debug(entry['category'])
    itemStr = itemT.substitute(
	entryTitle=saxutils.escape(entry['title']),
        entryURL='',
	entryAuthor=user,
	category=entry['category'],
	entryContent=entry['content'],
        entryId=entryId,
	postDate=entry['date'].strftime('%Y-%m-%d %H:%M:%S'),
	postDateGMT=(entry['date']-timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S'),
	pubDate=entry['date'].strftime('%a, %d %b %Y %H:%M:%S +0800'),
        comments=commentsStr)
    entryId-=1
    #logging.debug(itemStr)
    f.write(itemStr)
    
def exportFoot(f):
    f.write("""
</channel>
</rss>
""")
    f.close()
    
def main():
    #main procedure begin
    parser = OptionParser()
    parser.add_option("-s","--source",action="store", type="string",dest="srcURL",help="source msn/live space address")
    parser.add_option("-f","--startfrom",action="store", type="string",dest="startfromURL",help="a permalink in source msn/live space address for starting with, if this is specified, srcURL will be ignored.")    
    parser.add_option("-d","--dest",action="store",type="string",dest="destURL",help="destination wordpress blog address (must point to xmlrpc.php). If this isn't provided, only export xml")
    parser.add_option("-u","--user",action="store",type="string",dest="user",default="yourusername",help="username for logging into destination wordpress blog")
    parser.add_option("-p","--password",action="store",type="string",dest="passw",default="yourpassword",help="password for logging into destination wordpress blog")
    parser.add_option("-x","--proxy",action="store",type="string",dest="proxy",help="http proxy server, only for connecting live space.I don't know how to add proxy for metaWeblog yet. So this option is probably not useful...")
    parser.add_option("-t","--datetimepattern",action="store",dest="datetimepattern",default="%Y-%m-%d %H:%M",help="The datetime pattern of livespace, default to be %Y/%m/%d %H:%M. Check http://docs.python.org/lib/module-time.html for time formatting codes. Make sure to quote the value in command line.")
    parser.add_option("-b","--draft",action="store_false",dest="draft",default=True,help="as published posts or drafts after transfering,default to be published directly")
    parser.add_option("-l","--limit",action="store",type="int",dest="limit",help="limit number of transfered posts, you can use this option to test")
    parser.add_option("-m","--mode",action="store",type="string",dest="mode",default="all",help="Working mode, 'all' or 'commentsOnly'. Default is 'all'. Set it to 'commentsOnly' if you have used earlier version of this script to move posts. Set it to 'postsOnly' if you can't upload the comments-post page to your dest WordPress blog so can't move comments")
    parser.add_option("-c","--postcommentsurl",action="store",type="string",default='',dest="postCommentsURL",help="The URL for posting comments, usually should be the URL of 'my-wp-comments-post.php' provided with this script. If this option isn't set, program will use destURL and the default page name to decide.")    
    parser.add_option("-a","--maxDstEntryID",action="store",type="int",default='100',dest="maxDstEntryID",help="Use this parameter to specify the MAX post id of your destination blog")    
    (options, args) = parser.parse_args()
    
    
    #export all options variables
    for i in dir(options):
        exec i+" = options."+i
    #decide postCommentsURL
    if destURL:
        if len(postCommentsURL)==0:
            postCommentsURL = destURL.rsplit('/',1)[0]+'/my-wp-comments-post.php'
            logging.info('Set postCommentsURL to %s', postCommentsURL)
    #add proxy
    if proxy:
        proxy_handler = urllib2.ProxyHandler({'http': proxy})
        opener = urllib2.build_opener(proxy_handler)
        urllib2.install_opener(opener)
        logging.info("Set proxy to %s",proxy)
    #test username/password and desturl valid
    if destURL:
        logging.debug('Test destination blog address %s',destURL)
        server=xmlrpclib.ServerProxy(destURL,verbose = 0)
        blogid = int(1)
        try:
            server.metaWeblog.getUsersBlogs(blogid,user,passw)
            logging.info('Connect to dest blog successfully')
        except xmlrpclib.ProtocolError,xmlrpclib.ResponseError:
            logging.error("Error while checking username %s. Possible reasons are:",user)
            logging.error(" - The weblog doesn't exist")
            logging.error(" - Path to xmlrpc server is incorrect")
            logging.error("Check for typos.")
            sys.exit(2)
        except xmlrpclib.Fault:
            logging.error("Error while checking username %s. Possible reasons are:",user)
            logging.error(" - your weblog doesn't support the MetaWeblog API")
            logging.error(" - your weblog doesn't like the username/password combination you've provided.")
            sys.exit(2)
    #Load or Fetch dst blog entries dict (title and id)
    if destURL and mode == 'commentsOnly':
        logging.info('Comments Only mode, try to get a dict of dest blog entries')
        loadedDump = False
        if os.path.exists('DstEntryDict.dump') :
            try :
                f = open('DstEntryDict.dump')
                dstBlogEntryDict = pickle.load(f)
                f.close()
                loadedDump = True
                logging.info('Finished Loading Destination Blog Entries from local cache')
            except Exception:
                logging.info('Loading DstEntryDict.dump failed, begin to fetch')
                loadedDump = False
        if not loadedDump :
            f = open('DstEntryDict.dump','w')
            dstBlogEntryDict = getDstBlogEntryList(server,user,passw,maxDstEntryID)
            pickle.dump(dstBlogEntryDict,f)
            f.close()
            logging.info('Finished Fetching Destination Blog Entries from site, and saved to local for caching')
    global entries
    global categories
    cacheFile = None
    #If there is a cache file, load it and resume from the last post in it
    if not startfromURL and os.path.exists('entries.cache'):
        logging.info('Found cache file')
        cacheFile = open('entries.cache','r')
        try:
            while True:
                entry = pickle.load(cacheFile)
                logging.info('Load entry from cache file with title %s',entry['title'])
                entries.append(entry)
        except (pickle.PickleError,EOFError):
            logging.info("No more entries in cache file for loading")
            cacheFile.close()
            cacheFile = open('entries.cache', 'a+')
        if len(entries)>0:
            startfromURL = entries[-1]['permalLink']
            logging.info("Will start fetching from %s",startfromURL)
    #connect src blog and find first permal link
    if srcURL :
        pass
    else :	
        srcURL="http://blog.csdn.net/davelv/"
    if startfromURL :
        permalink = startfromURL
        logging.info('Start fetching from %s',startfromURL)
    elif srcURL:
        permalink = find1stPermalink(srcURL)
    else:
        logging.error("Error, you must give either srcURL or startfromURL")
        sys.exit(2)
    #main loop, retrieve every blog entry and post to dest blog
    count = 0
    if not cacheFile:
        cacheFile = open('entries.cache','w')
    try:
        while permalink:
            i=fetchEntry(permalink,datetimepattern,mode)
            if 'title' in i:
                logging.info("Got a blog entry titled %s with %d comments successfully",i['title'], len(i['comments']))
            if destURL:
                wpost = {}
                wpost['description']=i['content']
                wpost['title'] = i['title']
                wpost['dateCreated']=i['date']
                if mode == 'all':
                    pID = publishPost(server,blogid,user,passw,wpost,draft)
                    publishComments(entry=i,pID=pID,postCommentsURL=postCommentsURL)
                elif mode == 'postsOnly':
                    publishPost(server,blogid,user,passw,wpost,draft)
                else : #mode='commentsOnly'
                    publishComments(entry=i,dstBlogEntryDict=dstBlogEntryDict,postCommentsURL=postCommentsURL)
                    
            entries.append(i)
            #pickle.dump(i,cacheFile)
            logging.debug("-----------------------")
            if 'prevLink' in i :
                    permalink = i['prevLink']
            else :
                    break
            count+=1
            if count > 5:
		break
            if limit and count >= limit : break
    finally:
        cacheFile.close()
    #get blog info and export header
    blogInfoDic = {}
    if srcURL:
        blogInfoDic['blogURL']=srcURL
    elif startfromURL:
        blogInfoDic['blogURL'] = startfromURL.split('com/',1)[0]+'com/'
    else:
        logging.error("Error, you must give either srcURL or startfromURL")
        sys.exit(2)
    logging.info('Blog URL is %s',blogInfoDic['blogURL'])
    blogInfoDic['nowTime']=datetime.now().strftime('%Y-%m-%d %H:%M')
    page = urllib2.urlopen(urllib2.Request(blogInfoDic['blogURL'],headers=userAgent));
    soup = BeautifulSoup(page)
    blogInfoDic['blogTitle']= replaceUnicodeNumbers(u'' + soup.find(id='blog_title').h1.a.string)
    logging.debug('Blog Title is %s',blogInfoDic['blogTitle'])
    exportFileName = 'export_'+datetime.now().strftime('%m%d%Y-%H%M')+'.xml'
    f = codecs.open(exportFileName,'w','utf-8')
    if f:
        logging.info('Export XML to file %s',exportFileName)
    else:
        logging.error("Can't open export file %s for writing",exportFileName)
        sys.exit(2)
    exportHead(f,blogInfoDic,categories)
    logging.debug('Exported header')
    #export entries
    for entry in entries:
        exportEntry(f,entry,user)
    #export Foot
    exportFoot(f)
    logging.debug('Exported footer')
    #Delete cache file
    os.remove('entries.cache')
    logging.info("Deleted cache file")
    logging.info("Finished! Congratulations!")

if __name__=="__main__":
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
    except:
        logging.exception("Unexpected error")
        raise

