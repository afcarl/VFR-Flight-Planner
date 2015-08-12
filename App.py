from flask import Flask, render_template, g, Markup, session, request, redirect, make_response
from flask_wtf import Form
from flask_mail import Mail, Message
from wtforms import StringField
from wtforms.validators import DataRequired
from FlightFiles import *
from forms import *
from flask.ext.cache import Cache 
from pdf import *
import os, time

"""
	VFR-Flight-Planner

	@author 	Andrew Milich 
	@version 	0.4 

	This application is designed to simplify the extensive planning prior to VFR flghts. 
	It finds cities and airports along the route to ensure a pilot remains on course, 
	finds weather throughout the trip, and corrects for magnetic deviation in each 
	segment. After creating an elevation map, the application will detect potential 
	altitude hazards and suggest a new cruising altitude. A user can also perform simple 
	weight, balance, performance, and weather calculations.

	Written Summer 2015.  

	Potential features: 
		* Diversion airports 
		* Fuel stops (unicom, etc.)
			* [DONE] Frequencies 
		* [DONE] Simple weight and balance (using dynamic form)
			* C172 and generalized 
		* Add loading page for update route 
		* Custom airplane features dynamically transferred to weight/balance 
		* Airplane performance statistics (at least C172SP NAV III)
		* User friendly tutorial 
		* [DONE] Elevation awareness and maps 
		* [DONE] Climbs across waypoints 
		* [DONE] Save routes as PDF 
			* [DONE] Save weather, frequencies as well 

	Possible improvements: 
		* Search for waypoints after TOC 
"""

app = Flask(__name__)
app.secret_key = 'xbf\xcb7\x0bv\xcf\xc0N\xe1\x86\x98g9\xfei\xdc\xab\xc6\x05\xff%\xd3\xdf'
cache = Cache(app,config={'CACHE_TYPE': 'simple'})

gmail_name = 'codesearch5@gmail.com'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = gmail_name
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_KEY')
mail = Mail(app)

"""
Email feedback from contact form. 
"""
@app.route('/contact', methods=('GET', 'POST'))
def contact():
    form = ContactForm()

    if request.method == 'POST':
        if form.validate() == False:
        	form = searchform()
        	return render_template('index.html', form=form)
        else:
            msg = Message("Message from your visitor " + form.name.data, sender=form.email.data, recipients=['codesearch5@gmail.com'])
            msg.body = """
            From: %s <%s>,
            %s
            """ % (form.name.data, form.email.data, form.message.data)
            mail.send(msg)
            form = searchform()
            return render_template('index.html', form=form)
    elif request.method == 'GET':
        return render_template('contact.html', form=form)

@app.route('/test')
def testform():
	options = getAirportOptions()
	form = searchform()
	return render_template('route_test.html', options=Markup(options), form=form)

"""
Converts flight plan page with map, elevation diagram, and table of segments into printable PDF. 
"""
@app.route('/saveplan', methods=['GET'])
def savePlan(): 
	try: 
		myRoute = cache.get('myRoute')
		environment = cache.get('env_origin')
		environment2 = cache.get('env_dest')
		map_content = str(makeStaticMap(myRoute[2].courseSegs, myRoute[2].destination)).replace("\n", "")
		route_pdf = gen_pdf(render_template('pdfroute.html', map=Markup(map_content), theRoute = myRoute[2].courseSegs, \
			elevation=myRoute[3], freqs=myRoute[5], env=environment, env2=environment2, airplane=cache.get('airplane')))
		response = make_response(route_pdf)
		response.mimetype = 'application/pdf'
		response.headers["Content-Disposition"] = "attachment; filename=route.pdf"
		return response
	except Exception, e: 
		print str(e)
		return render_template('fail.html', error="pdf")

"""
After a user enters a new waypoint, this function updates the route, climb, and maps. 
"""
@app.route('/update', methods = ['POST'])
def update():
	newLoc = str(request.form['place']).upper()
	num = str(request.form['num'])
	try: 
		myRoute = cache.get('myRoute')
		myRoute = changeRoute(myRoute[1], int(num)-1, str(newLoc), session['ORIG'], \
			session['DEST'], session['ALT'], session['SPD'], session['CLMB'], \
			session['CLMB_SPD'], session['REGION'])
		map_content = str(myRoute[0])
		cache.set('myRoute', myRoute, timeout=500)

		forms = []
		counter = 0
		for x in range(len(myRoute[2].courseSegs)):
			forms.append(placeform(place=myRoute[2].courseSegs[x].to_poi.name, num=x))

		cache.set('myRoute', myRoute, timeout=500)
		return render_template('plan.html', map=Markup(map_content), theRoute = myRoute[2].courseSegs, forms=forms, \
			page_title = "Your Route", elevation=myRoute[3], freqs=myRoute[5], zipcode=myRoute[6], \
			airplane=cache.get('airplane'), dest = myRoute[2].destination)
	except Exception, e: 
		print str(e)
		return render_template('fail.html', error="waypoint")

"""
Once the user submits aircraft data and basic route information, a route is generated with 
relevant maps and displayed on the screen. 
"""
@app.route('/fplanner', methods = ['POST'])
def search():
	# this will get the weight and balance parameters
	weights = []
	try: 
		for x in range(1, 10): 
			w = request.form['w%s' % (x)] 
			a = request.form['a%s' % (x)] 
			if a == "" or w == "": 
				break
			weights.append(Weight(float(w), float(a)))
	except: 
		pass # this is natural - there is a finite number of weight/arm boxes 

	plane_type = request.form['plane_type']
	airplane = Airplane(plane_type, weights)
	print airplane
	cache.set('airplane', airplane, timeout=500)

	try:
		startTime = time.time()
		# basic route information 
		airp1 = request.form['orig'].upper() 
		airp2 = request.form['dest'].upper()
		region = request.form['region'].upper()
		# there will always be an answer to the above 3 - they are select fields 
		if getDist(airp1, airp2) > 400: 
			return render_template('fail.html', error="distance")
		altitude = request.form['alt']
		if altitude == "": 
			altitude = "3500"
		speed = request.form['speed']
		if speed == "": 
			speed = "110"
		climb_dist = request.form['climb']
		if climb_dist == "": 
			climb_dist = 5
		else: 
			climb_dist = float(climb_dist)
		climb_speed = request.form['climb_speed']
		if climb_speed == "": 
			climb_speed = 75
		else: 
			climb_speed = float(climb_speed)

		print 'Routing from %s to %s at %s kts and %s feet.' % (airp1, airp2, speed, altitude)

		env_origin = Environment(airp1)
		env_dest = Environment(airp2)
		# these environments can be accessed when generating weather PDF and displaying messages
		# cache.set('airplane', airplane, timeout=500)
		cache.set('env_origin', env_origin, timeout=500)
		cache.set('env_dest', env_dest, timeout=500)
	
		session['ORIG'] = airp1
		session['DEST'] = airp2
		session['ALT'] = altitude
		session['SPD'] = speed
		session['REGION'] = region
		session['CLMB'] = climb_dist
		session['CLMB_SPD'] = climb_speed
	
		myRoute = createRoute(airp1, airp2, altitude, speed, environments=[env_origin, env_dest], \
			climb_dist=climb_dist, climb_speed=climb_speed, region=region)
		map_content = str(myRoute[0])
	
		forms = [] # used for changing waypoints 
		for x in range(len(myRoute[2].courseSegs)):
			forms.append(placeform(place=myRoute[2].courseSegs[x].to_poi.name, num=x))
		
		cache.set('myRoute', myRoute, timeout=500)
		messages = myRoute[4]
	
		if not (env_origin.weather == "NONE"): 
			if env_origin.skyCond == 'IFR': 
				messages.append("Origin is in IFR conditions")
			elif env_origin.skyCond == 'SVFR': 
				messages.append("Origin is in SVFR conditions")
		
			if env_dest.skyCond == 'IFR': 
				messages.append("Destination is in IFR conditions")
			elif env_dest.skyCond == 'SVFR': 
				messages.append("Destination is in SVFR conditions")
	
		showMsgs = True if(len(messages) is not 0) else False
		
		# mail me a copy of the route for recordkeeping 
		try: 
			msg = Message("Route planned from " + airp1 + " to " + airp2, sender="codesearch5@gmail.com", recipients=['codesearch5@gmail.com']) 
			mail.send(msg)
		except: 
			pass

		# need to know this 
		elapsedTime = time.time() - startTime
		print 'function [{}] finished in {} ms'.format('route', int(elapsedTime * 1000))

		return render_template('plan.html', map=Markup(map_content), theRoute = myRoute[2].courseSegs, forms=forms,\
			page_title = "Your Route", elevation=myRoute[3], messages=messages, showMsgs = showMsgs, freqs=myRoute[5], \
			zipcode=myRoute[6], airplane=airplane, dest = myRoute[2].destination)
	except Exception, e: 
		print str(e)
		return render_template('fail.html', error="creation")

"""
Initialize homepage with entry form. 
"""
@app.route('/')
def init():
	form = searchform()
	return render_template('index.html', form=form)

"""
Run app. 
"""
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.debug = True
    app.run(host='0.0.0.0', port=port)