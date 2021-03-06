"""
slowmovie


MIT License

Copyright (c) 2020 Mike Szczys

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import re
import subprocess
import json
import paho.mqtt.client as mqtt

'''
Get framecount (minus one for zero index:
   ffmpeg -i input.mp4 -map 0:v:0 -c copy -f null -
'''
totalFrames = 196455
sourceFrameate = 23.98

'''
Everything will happen in the working directory (remember trailing slash!).
Make a symlink to the video in this directory
'''
workingDir = "/home/mike/compile/slowmovie/"
videoFile = "input.mkv"
mqttBrokerAddr = "192.168.1.135"
mqttTopic = "slowmovie/frame"

#Don't edit these:
framecountJSON = workingDir + "framecount.json"
videoFile = workingDir + videoFile
frameCapture = workingDir + "frame.png"
inputXBMfile = workingDir + "frame.xbm"
outputXBMfile = workingDir + "output.xbm" #this is likely deprecated

def processNextFrame():
    '''
    Workflow:
    * lookup next frame number
    * grab frame
    * convert to XBM
    * flip endianness and invert
    * publish to MQTT
    * increment framecount and save back to json
    '''

    #Import JSON
    framecount = getSavedFramecount(framecountJSON)
    if framecount == None:
        #Error getting JSON, try to generate a new one
        print("Trying to generate new JSON file")
        framecount = {'totalframes': totalFrames, 'nextframe': 0}
        if (saveFramecount(framecountJSON, framecount) == False):
            print("Abort: JSON file cannot be saved")
            return

    #Grab next frame
    if harvestFrame(videoFile, sourceFrameate, framecount['nextframe']) == None:
        print("Abort: Unable to grab next frame from video")
        return

    #Convert to XBM
    if convertToXBM(frameCapture) == None:
        print("Abort: Unable to convert captured frame to XBM")
        return

    #Get formatted string from XBM data
    xbmArray = getXBM(inputXBMfile)
    if xbmArray == None:
        print("Abort: Unable to import XBM array data")
    mqttMessage = outputSingleString(xbmArray)
    #print(mqttMessage)

    #Publish message to MQTT
    publishMQTT(mqttBrokerAddr, mqttTopic, mqttMessage)

    #Increment framecount and save
    framecount['nextframe'] += 1
    if framecount['nextframe'] >= framecount['totalframes']:
        framecount['nextframe'] = 0
    if saveFramecount(framecountJSON, framecount) == False:
        print("Abort: failed to save new framecount")
        return
    else:
        print("Successfully sent next frame via MQTT")
    

def getSavedFramecount(jsonfile):
    #Import JSON to get next frame count
    try:
        with open(jsonfile) as f:
            framecount = json.load(f)
    except:
        print("Unable to open JSON file %s" % framecountJSON)
        return None
    return framecount


def saveFramecount(jsonfile, countDict):
    #Export JSON for frame count
    try:
        with open(jsonfile, 'w') as f:
            json.dump(countDict, f)
        print("Successfully generated JSON file")
    except:
        print("Unable to write JSON file %s" % framecountJSON)
        return False
    return True

def invertAndSwitchEndian(hexval):
    """
    Take a value and return the inverse, endian-flipped, hex value of it
    """
    if type(hexval) == str:
        stringVal = format(int(hexval[-2:],16), '#010b')[2:]
    else:
        stringVal = format(hexval, '#010b')[2:]
    #newVal = stringVal[::-1]
    invertedVal = ''
    for i in stringVal[::-1]:
        invertedVal += '0' if i == '1' else '1'
    return format(int(invertedVal,2),'#04X')

def fixHexArray(hexList):
    """
    XBM files are almost what we need but they are inverted and wrong-endian. This fixes it.
    """
    print("imgArray = {")
    print("    ",end='')
    for i in range(len(hexList)):
        print(invertAndSwitchEndian(hexList[i]),end='')
        if (i+1)%16 == 0:
            print(',\n    ',end='')
            
        else:
            print(',',end='')
    print('')
    print("};")

def outputSingleString(hexList):
    """
    XBM files are almost what we need but they are inverted and wrong-endian. This fixes it.
    """
    outString = ""
    for i in range(len(hexList)):
        outString += invertAndSwitchEndian(hexList[i])[-2:]
    return outString

def getXBM(filename):
    """
    Read in all the hex values from an XBM image file
    """
    try:
        with open(filename) as file:  
            data = file.read()
    except:
        return []

    hexvalues = re.findall(r'0X[0-9A-F]+', data, re.I)
    return hexvalues

def harvestFrame(video, frameRate, frameCount):
    cadence = 1000/frameRate
    frameMilliseconds = frameCount * cadence
    millis=int(frameMilliseconds%1000)
    seconds=int((frameMilliseconds/1000)%60)
    minutes=int((frameMilliseconds/(1000*60))%60)
    hours=int((frameMilliseconds/(1000*60*60))%24)
    timestamp = str(hours) + ":" + str(minutes) + ":" + str(seconds) + "." + str(millis)

    cmd = '/usr/bin/ffmpeg -y -ss "' + timestamp + '" -i ' + videoFile + ' -frames:v 1 ' + frameCapture
    print(cmd)
    try:    
        subprocess.run(cmd, shell=True)
        return True
    except:
        print("FFMEG failed to grab a frame")
        return None

def convertToXBM(image):
    cmd = 'convert ' + frameCapture + ' -rotate -90 -resize "176x264^" -gravity center -crop 176x264+0+0 -dither FloydSteinberg ' + inputXBMfile
    print(cmd)

    try:
        subprocess.run(cmd, shell=True)
        return True
    except:
        print("Failed to convert image to XBM")
        return None

def publishMQTT(broker,topic,message):
    mqttBroker = broker
    client = mqtt.Client("slowmovie_frame_grabber")
    client.connect(mqttBroker)
    client.publish(topic, message)
    client.disconnect()
